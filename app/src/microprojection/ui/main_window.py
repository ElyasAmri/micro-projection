"""Application main window.

Stripped to a bare shell for a UI redesign: a titled window with an empty
central area. No menu bar, no status bar. All panels, views, tabs, and the
processing pipeline still live on disk under ``microprojection.ui`` and
``microprojection.processing``. Re-wire them into the central area as the new
design takes shape. The previous full layout is in git history (commit
2c9555a, ``ui/main_window.py``).
"""

import sys
from dataclasses import replace

import numpy as np
from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QSplitter,
    QWidget,
)

from microprojection.acquisition.camera import enumerate_cameras
from microprojection.acquisition.camera_settings import (
    CameraSettings,
    flicker_safe_exposure,
)
from microprojection.acquisition.projector import ProjectorController
from microprojection.config import AppConfig
from microprojection.patterns import generate_pattern
from microprojection.ui.camera_controller import CameraController
from microprojection.ui.camera_settings_dialog import CameraSettingsDialog
from microprojection.ui.device_watch import DeviceWatcher
from microprojection.ui.preview_view import PreviewView
from microprojection.ui.projector_settings_dialog import ProjectorSettingsDialog
from microprojection.ui.acquisition_controller import AcquisitionController
from microprojection.ui.projector_window import ProjectorWindow
from microprojection.ui.screens import projector_screens
from microprojection.ui.sidebar import Sidebar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MicroProjection. Fringe Projection Profilometry")
        self.resize(1280, 800)

        # Config and hardware.
        self._config = AppConfig()
        self._projector_window = None              # HDMI fringe display
        self._projector_ctl = ProjectorController()  # DLPC350 over USB
        # Last projection choice, so the settings modal reopens on it.
        self._projection = {
            "key": "none",
            "period": 32,
            "orientation": "vertical",
            "path": "",
        }

        self._camera = CameraController(parent=self)
        self._camera.fpsUpdated.connect(self._on_fps_updated)
        self._camera.error.connect(self._on_camera_error)
        # The preview pulls the latest frame from the controller on its own
        # timer (see PreviewView), so frames are never queued behind it. The
        # frameReady signal is left for the capture pipelines, which need every
        # frame; nothing listens to it during plain live preview.
        # Current camera configuration, restored from the last run and edited
        # via the settings dialog. This holds the user's intent; the exposure
        # actually applied is snapped to the projector refresh to avoid flicker
        # (see _effective_camera_settings). Seed the controller so the first
        # camera that starts already uses it.
        self._camera_settings = self._config.camera_settings
        self._camera.apply_settings(self._effective_camera_settings())

        # Populate the device list eagerly so the selector is ready.
        self._available_cameras = enumerate_cameras()

        # Central area.
        self.setCentralWidget(self._build_central())

        # Auto-refresh the device list on USB hot-plug instead of a button.
        self._device_watcher = DeviceWatcher(parent=self)
        self._device_watcher.changed.connect(self._rescan_cameras)
        QApplication.instance().installNativeEventFilter(self._device_watcher)

        # Refresh the projector list when a display is connected/disconnected.
        app = QApplication.instance()
        app.screenAdded.connect(self._rescan_screens)
        app.screenRemoved.connect(self._rescan_screens)

        # Press "r" to restart the app in a fresh process (reload code changes).
        self._restart_shortcut = QShortcut(QKeySequence("r"), self)
        self._restart_shortcut.activated.connect(self._restart_app)

    def _build_central(self) -> QWidget:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._sidebar = Sidebar()
        self._sidebar.deviceSelected.connect(self._select_device)
        self._sidebar.cameraSettingsRequested.connect(self._show_camera_settings)
        self._sidebar.projectorSelected.connect(self._select_projector)
        self._sidebar.projectorSettingsRequested.connect(self._show_projector_settings)
        self._acquisition = AcquisitionController(
            self._camera, self._sidebar, self,
            projector_window=lambda: self._projector_window,
            settings=self._effective_camera_settings,
            projection=lambda: self._projection,
            parent=self,
        )
        self._acquisition.status.connect(self._status)
        self._sidebar.phaseShiftRequested.connect(self._acquisition.run_phase_shift)
        self._sidebar.noiseTestRequested.connect(self._acquisition.run_noise_test)
        # Restore the projector first so its refresh rate is known before the
        # camera starts; the camera then starts once with the flicker-safe
        # exposure instead of being restarted right after to apply it.
        self._sidebar.set_projectors(
            self._enumerate_screens(), prefer_index=self._config.last_projector
        )
        # Default to no camera (off); restore the last-used one if it's present.
        self._sidebar.set_cameras(
            self._available_cameras, prefer_key=self._config.last_camera
        )

        # Main content area: the live camera preview fills the viewport. It
        # pulls the newest frame from the camera controller on its own timer.
        self._content = PreviewView(frame_source=self._camera.latest_frame)

        # Resizable split between the sidebar and the content area.
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._sidebar)
        self._splitter.addWidget(self._content)
        self._splitter.setStretchFactor(0, 0)   # sidebar keeps its width
        self._splitter.setStretchFactor(1, 1)   # content absorbs resizing
        self._splitter.setCollapsible(0, False)  # don't let the sidebar vanish
        width = self._config.sidebar_width or Sidebar.WIDTH
        self._splitter.setSizes([width, 10_000])
        self._splitter.splitterMoved.connect(self._on_splitter_moved)

        layout.addWidget(self._splitter)
        return central

    def _on_splitter_moved(self, *_):
        self._config.sidebar_width = self._splitter.sizes()[0]

    def _rescan_cameras(self):
        """Re-enumerate cameras after a USB hot-plug event.

        Skipped while a camera is streaming: PySpin cannot be safely
        re-enumerated during acquisition (a fresh GetCameras returns nothing and
        destabilizes the running device), and a USB3 camera starting
        acquisition itself raises a device-change event. enumerating then would
        drop and crash the active camera. A disconnect of the running camera
        surfaces through its error signal instead.
        """
        if self._camera.running:
            return
        self._available_cameras = enumerate_cameras()
        self._sidebar.set_cameras(
            self._available_cameras, prefer_key=self._config.last_camera
        )
        self._status(f"Device change: {len(self._available_cameras)} camera(s)")

    def _restart_app(self):
        """Relaunch the app in a fresh process so code changes take effect."""
        self._camera.stop()  # release the camera before the new process probes
        QProcess.startDetached(sys.executable, ["-m", "microprojection.app"])
        self.close()  # closeEvent cleans up; last window closing quits the app

    def _status(self, msg: str):
        """Report status. No status bar in the shell, so log to console.

        Re-point this at the new design's status widget once it exists. (Do
        NOT call self.statusBar(); it would silently recreate the bottom bar.)
        """
        print(f"[status] {msg}", flush=True)

    # Camera.

    def _select_device(self, backend: str, index: int):
        # Sentinel from the sidebar: "No camera" (or the active one unplugged).
        if index < 0 or not backend:
            self._camera.stop()
            self._content.clear()
            self._config.last_camera = None
            self._status("No camera")
            return
        # Selecting a camera turns it on (no separate start/stop controls).
        self._camera.select(backend, index)
        self._config.last_camera = (backend, index)
        self._status(f"Camera on: {backend} {index}")

    def _show_camera_settings(self):
        """Open the camera configuration modal seeded with the current settings."""
        dialog = CameraSettingsDialog(self._camera_settings, self)
        dialog.settingsChanged.connect(self._apply_camera_settings)
        dialog.exec()

    def _apply_camera_settings(self, settings: CameraSettings):
        """Store the edited settings, persist them, and push them to the camera
        (restarts a running camera so structural changes take effect).

        Auto-apply fires on every control change, including focus-out with no
        edit, so skip when nothing actually changed to avoid a needless restart.
        """
        if settings == self._camera_settings:
            return
        self._camera_settings = settings
        self._config.camera_settings = settings
        self._camera.apply_settings(self._effective_camera_settings())
        self._status("Camera settings applied")

    def _effective_camera_settings(self) -> CameraSettings:
        """The user's camera settings with the exposure snapped to a whole
        number of projector refresh periods, to cancel projector/camera flicker.

        Only adjusts manual exposure (not auto) and only when a projector with a
        known refresh rate is active. The stored/persisted settings keep the
        user's chosen exposure; only the value sent to the camera is snapped.
        """
        settings = self._camera_settings
        win = self._projector_window
        if settings.exposure_auto != "Off" or win is None:
            return settings
        hz = win.refresh_hz()
        snapped = flicker_safe_exposure(settings.exposure_time_us, hz)
        if abs(snapped - settings.exposure_time_us) < 1.0:
            return settings
        self._status(
            f"Exposure snapped to {snapped / 1000.0:.3f} ms "
            f"(whole frames at {hz:.2f} Hz) to avoid projector flicker"
        )
        return replace(settings, exposure_time_us=snapped)

    def _on_fps_updated(self, fps: float):
        self._status(f"FPS: {fps:.1f}")

    def _on_camera_error(self, msg: str):
        self._status(f"Camera error: {msg}")

    # Projector (HDMI display).

    def _enumerate_screens(self) -> list[dict]:
        """External displays usable as projector targets.

        Built-in panels and the primary desktop screen are hidden so only real
        projection displays (such as an HDMI projector) are offered. See
        ui/screens.py for how desktop screens are identified.
        """
        return projector_screens()

    def _rescan_screens(self, *_):
        self._sidebar.set_projectors(
            self._enumerate_screens(), prefer_index=self._config.last_projector
        )

    def _select_projector(self, index: int):
        """Project onto the chosen screen, or hide the window for -1."""
        if index < 0:
            self._hide_projector()
            self._config.last_projector = None
            self._status("No projector")
            return
        screens = QApplication.screens()
        if not 0 <= index < len(screens):
            return
        self._select_projector_screen(screens[index])
        self._config.last_projector = index

    def _show_projector_settings(self):
        """Open the projector modal to pick a temporary test projection."""
        dialog = ProjectorSettingsDialog(self._projection, self)
        dialog.projectionRequested.connect(self._project_pattern)
        dialog.projectionCleared.connect(self._clear_projection)
        dialog.exec()

    def _project_pattern(self, spec: dict):
        """Render the chosen test pattern or image onto the projector screen."""
        win = self._projector_window
        if win is None:
            self._status("Select a projector first")
            return
        width, height = win.target_size()
        if width <= 0 or height <= 0:
            self._status("Projector size unknown")
            return
        if spec.get("source") == "image":
            self._projection.update(key="image", path=spec.get("path", ""))
            if win.set_image_file(spec.get("path", "")):
                self._status("Projecting image")
            else:
                self._status("Could not load image")
            return
        kind = spec.get("pattern", "fringe")
        self._projection.update(
            key=kind,
            period=spec.get("period", 32),
            orientation=spec.get("orientation", "vertical"),
        )
        pattern = generate_pattern(
            kind, width, height,
            period=spec.get("period", 32),
            orientation=spec.get("orientation", "vertical"),
        )
        win.update_pattern(pattern)
        self._status(f"Projecting {kind}")

    def _clear_projection(self):
        """Blank the projector (project black)."""
        self._projection["key"] = "none"
        win = self._projector_window
        if win is None:
            return
        width, height = win.target_size()
        if width > 0 and height > 0:
            win.update_pattern(np.zeros((height, width), dtype=np.uint8))
            self._status("Projector blanked")

    def _select_projector_screen(self, screen):
        if self._projector_window is None:
            self._projector_window = ProjectorWindow()
        self._projector_window.move_to_screen(screen)
        self._status(f"Projector on {screen.name()}")
        # The projector's refresh rate sets the flicker-safe exposure, so
        # re-apply the camera config now that it (or the screen) is known.
        self._camera.ensure_settings(self._effective_camera_settings())

    def _show_projector(self):
        if self._projector_window is None:
            screens = QApplication.screens()
            target = next(
                (s for s in screens if s != QApplication.primaryScreen()),
                screens[0],
            )
            self._select_projector_screen(target)
        else:
            self._projector_window.showFullScreen()

    def _hide_projector(self):
        if self._projector_window is not None:
            self._projector_window.hide()

    # Projector (DLPC350 USB control).

    def _projector_usb(self, action, success_msg: str):
        ctl = self._projector_ctl
        if not ctl.available:
            self._status(
                "USB projector control unavailable. Install: pip install -e .[hardware]"
            )
            return False
        try:
            action()
        except Exception as exc:  # noqa: BLE001. surface any pyusb/backend error
            self._status(f"Projector USB error: {exc}")
            return False
        self._status(success_msg)
        return True

    def _projector_connect(self):
        from microprojection.acquisition.projector import enumerate_projectors
        ctl = self._projector_ctl
        if not ctl.available:
            self._status(
                "USB projector control unavailable. Install: pip install -e .[hardware]"
            )
            return
        devices = enumerate_projectors()
        if devices:
            msg = f"PRO4500 detected on USB (DLPC350). {len(devices)} device(s)"
        else:
            msg = "No DLPC350 device found. Check USB and libusb backend (Zadig)"
        self._status(msg)

    def _projector_power_up(self):
        self._projector_usb(self._projector_ctl.power_up, "Projector powered up")

    def _projector_power_down(self):
        self._projector_usb(self._projector_ctl.power_down, "Projector in standby")

    def _projector_video_mode(self):
        self._projector_usb(self._projector_ctl.video_mode, "Projector in video mode")

    def _projector_stop_sequence(self):
        self._projector_usb(
            self._projector_ctl.stop_sequence, "Pattern sequence stopped"
        )

    # Shutdown.

    def closeEvent(self, event):
        if self._projector_ctl.available and self._projector_ctl.in_pattern_mode:
            try:
                self._projector_ctl.video_mode()
            except Exception:  # noqa: BLE001. best effort on shutdown
                pass
        if self._projector_window is not None:
            self._projector_window.close()
        self._camera.stop()
        super().closeEvent(event)
