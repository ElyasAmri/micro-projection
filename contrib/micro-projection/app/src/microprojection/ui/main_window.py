"""Application main window.

Stripped to a bare shell for a UI redesign: a titled window with an empty
central area -- no menu bar, no status bar. All panels, views, tabs, and the
processing pipeline still live on disk under ``microprojection.ui`` and
``microprojection.processing`` -- re-wire them into the central area as the new
design takes shape. The previous full layout is in git history (commit
2c9555a, ``ui/main_window.py``).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QSplitter,
    QWidget,
)

from microprojection.acquisition.camera import enumerate_cameras
from microprojection.acquisition.projector import ProjectorController
from microprojection.config import AppConfig
from microprojection.ui.camera_controller import CameraController
from microprojection.ui.device_watch import DeviceWatcher
from microprojection.ui.projector_window import ProjectorWindow
from microprojection.ui.sidebar import Sidebar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MicroProjection - Fringe Projection Profilometry")
        self.resize(1280, 800)

        # -- Config + hardware --
        self._config = AppConfig()
        self._projector_window = None              # HDMI fringe display
        self._projector_ctl = ProjectorController()  # DLPC350 over USB

        self._camera = CameraController(parent=self)
        self._camera.fpsUpdated.connect(self._on_fps_updated)
        self._camera.error.connect(self._on_camera_error)

        # Populate the device list eagerly so the selector is ready.
        self._available_cameras = enumerate_cameras()

        # -- Central area --
        self.setCentralWidget(self._build_central())

        # Auto-refresh the device list on USB hot-plug instead of a button.
        self._device_watcher = DeviceWatcher(parent=self)
        self._device_watcher.changed.connect(self._rescan_cameras)
        QApplication.instance().installNativeEventFilter(self._device_watcher)

    def _build_central(self) -> QWidget:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._sidebar = Sidebar()
        self._sidebar.deviceSelected.connect(self._select_device)
        # Default to no camera (off); restore the last-used one if it's present.
        self._sidebar.set_cameras(
            self._available_cameras, prefer_name=self._config.last_camera
        )

        # Main content area (to be designed -- preview, results, etc.).
        self._content = QWidget()

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
        """Re-enumerate after a hot-plug event; sidebar keeps the active device
        selected if it survived, so this won't disturb a running camera."""
        self._available_cameras = enumerate_cameras()
        self._sidebar.set_cameras(
            self._available_cameras, prefer_name=self._config.last_camera
        )
        self._status(f"Device change: {len(self._available_cameras)} camera(s)")

    def _status(self, msg: str):
        """Report status. No status bar in the shell -- log to console.

        Re-point this at the new design's status widget once it exists. (Do
        NOT call self.statusBar() -- it would silently recreate the bottom bar.)
        """
        print(f"[status] {msg}", flush=True)

    # -- Camera ------------------------------------------------------------

    def _select_device(self, backend: str, index: int):
        # Sentinel from the sidebar: "No camera" (or the active one unplugged).
        if index < 0 or not backend:
            self._camera.stop()
            self._config.last_camera = None
            self._status("No camera")
            return
        # Selecting a camera turns it on (no separate start/stop controls).
        self._camera.select(backend, index)
        self._config.last_camera = self._camera_name(backend, index)
        self._status(f"Camera on: {backend} {index}")

    def _camera_name(self, backend: str, index: int) -> str | None:
        """Stable display name for a device, used to remember the selection."""
        for cam in self._available_cameras:
            if cam["backend"] == backend and cam["index"] == index:
                return cam["name"]
        return None

    def _on_fps_updated(self, fps: float):
        self._status(f"FPS: {fps:.1f}")

    def _on_camera_error(self, msg: str):
        self._status(f"Camera error: {msg}")

    # -- Projector (HDMI display) ------------------------------------------

    def _select_projector_screen(self, screen):
        if self._projector_window is None:
            self._projector_window = ProjectorWindow()
        self._projector_window.move_to_screen(screen)
        self._status(f"Projector on {screen.name()}")

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

    # -- Projector (DLPC350 USB control) -----------------------------------

    def _projector_usb(self, action, success_msg: str):
        ctl = self._projector_ctl
        if not ctl.available:
            self._status(
                "USB projector control unavailable - install: pip install -e .[hardware]"
            )
            return False
        try:
            action()
        except Exception as exc:  # noqa: BLE001 - surface any pyusb/backend error
            self._status(f"Projector USB error: {exc}")
            return False
        self._status(success_msg)
        return True

    def _projector_connect(self):
        from microprojection.acquisition.projector import enumerate_projectors
        ctl = self._projector_ctl
        if not ctl.available:
            self._status(
                "USB projector control unavailable - install: pip install -e .[hardware]"
            )
            return
        devices = enumerate_projectors()
        if devices:
            msg = f"PRO4500 detected on USB (DLPC350) - {len(devices)} device(s)"
        else:
            msg = "No DLPC350 device found - check USB and libusb backend (Zadig)"
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

    # -- Shutdown ----------------------------------------------------------

    def closeEvent(self, event):
        if self._projector_ctl.available and self._projector_ctl.in_pattern_mode:
            try:
                self._projector_ctl.video_mode()
            except Exception:  # noqa: BLE001 - best effort on shutdown
                pass
        if self._projector_window is not None:
            self._projector_window.close()
        self._camera.stop()
        super().closeEvent(event)
