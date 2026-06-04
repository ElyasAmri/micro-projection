import time

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from microprojection.acquisition.camera import (
    OpenCVCameraThread,
    PySpinCameraThread,
    enumerate_cameras,
)
from microprojection.acquisition.projector import ProjectorController
from microprojection.core import paper_specs
from microprojection.core.datatypes import CaptureFrame
from microprojection.ui.panels.projector_panel import ProjectorPanel
from microprojection.export import save_report
from microprojection.processing.pipeline import PipelineThread
from microprojection.ui.panels.parameter_panel import ParameterPanel
from microprojection.ui.panels.results_panel import ResultsPanel
from microprojection.ui.tabs.calibration_tab import CalibrationTab
from microprojection.ui.views.camera_view import CameraView
from microprojection.ui.views.projection_view import ProjectionView
from microprojection.ui.views.result_view import ResultView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MicroProjection - Fringe Projection Profilometry")
        self.resize(1280, 800)

        # -- Projector (USB only; no HDMI extended-display path) --
        self._projector_ctl = ProjectorController()  # DLPC350 over USB

        # -- Widgets --
        self._calibration_tab = CalibrationTab()
        self._projection_view = ProjectionView()
        self._projector_panel = ProjectorPanel(self._projector_ctl)
        self._camera_view = CameraView()
        self._result_view = ResultView()
        self._parameter_panel = ParameterPanel()
        self._results_panel = ResultsPanel()
        self._latest_result = None  # last PipelineResult, used by Export Report

        # -- Projected-fringe tab: pattern preview + projector controls --
        self._projection_tab = QWidget()
        _proj_layout = QVBoxLayout(self._projection_tab)
        _proj_layout.setContentsMargins(0, 0, 0, 0)
        _proj_layout.addWidget(self._projection_view, stretch=3)
        _proj_layout.addWidget(self._projector_panel, stretch=2)

        # -- Synced-capture state --
        self._latest_capture_frame = None
        self._capturing = False
        self._cap_frames: list[np.ndarray] = []
        self._cap_step = 0
        self._cap_n = 0
        self._cap_params: dict = {}
        self._cap_wait_ticks = 0
        self._cap_timer = QTimer(self)
        self._cap_timer.timeout.connect(self._on_capture_tick)

        # -- Layout --
        # Left: top-level workflow tabs (in execution order: calibrate, project,
        # capture, reconstruct).
        self._tabs = QTabWidget()
        self._tabs.addTab(self._calibration_tab, "Calibration")
        self._tabs.addTab(self._projection_tab, "Projected Fringe")
        self._tabs.addTab(self._camera_view, "Received Fringe")
        self._tabs.addTab(self._result_view, "Reconstruction")

        # Right: parameters (top) + roughness (bottom)
        right_widget = QWidget()
        right_widget.setMinimumWidth(360)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        right_layout.addWidget(self._parameter_panel, stretch=3)
        right_layout.addWidget(self._results_panel, stretch=1)

        # Outer: tabs + right panel
        outer_splitter = QSplitter(Qt.Orientation.Horizontal)
        outer_splitter.addWidget(self._tabs)
        outer_splitter.addWidget(right_widget)
        outer_splitter.setStretchFactor(0, 3)
        outer_splitter.setStretchFactor(1, 1)

        self.setCentralWidget(outer_splitter)

        # -- Status bar --
        self._fps_label = QLabel("FPS: --")
        self._pipeline_label = QLabel("Pipeline: idle")
        self.statusBar().addPermanentWidget(self._fps_label)
        self.statusBar().addPermanentWidget(self._pipeline_label)

        # -- Threads --
        self._camera_thread = None
        self._pipeline_thread = PipelineThread(parent=self)

        # -- Signals --

        self._pipeline_thread.result_ready.connect(self._result_view.update_result)
        self._pipeline_thread.result_ready.connect(self._results_panel.update_roughness)
        self._pipeline_thread.result_ready.connect(self._on_pipeline_result)

        self._parameter_panel.parameters_changed.connect(
            self._pipeline_thread.update_params
        )
        self._parameter_panel.parameters_changed.connect(self._update_fringe_pattern)
        self._calibration_tab.calibration_changed.connect(self._on_calibration_changed)

        # Projector panel -> handlers
        self._projector_panel.detectRequested.connect(self._projector_connect)
        self._projector_panel.powerUpRequested.connect(self._projector_power_up)
        self._projector_panel.powerDownRequested.connect(self._projector_power_down)
        self._projector_panel.patternModeRequested.connect(self._projector_pattern_mode_panel)
        self._projector_panel.stopSequenceRequested.connect(self._projector_stop_sequence)
        self._projector_panel.captureRequested.connect(self._on_capture_requested)

        # -- Menu bar --
        self._build_menus()

        # Send initial parameters
        self._pipeline_thread.update_params(self._parameter_panel.get_params())

    def _build_menus(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction("&Export Report...", self._on_export_report)
        file_menu.addSeparator()
        file_menu.addAction("&Quit", self.close)

        camera_menu = menu_bar.addMenu("&Camera")
        self._device_menu = camera_menu.addMenu("Select &Device")
        camera_menu.addSeparator()
        camera_menu.addAction("&Start", self._start_camera)
        camera_menu.addAction("S&top", self._stop_camera)
        camera_menu.addSeparator()
        camera_menu.addAction("&Refresh Devices", self._refresh_devices)

        self._refresh_devices()

        # DLPC350 USB control (Wintech PRO4500). The projector is USB-only —
        # no HDMI extended-display path.
        projector_menu = menu_bar.addMenu("&Projector")
        projector_menu.addAction("&Connect / Detect", self._projector_connect)
        projector_menu.addSeparator()
        projector_menu.addAction("Power &Up", self._projector_power_up)
        projector_menu.addAction("Power &Down", self._projector_power_down)
        projector_menu.addSeparator()
        projector_menu.addAction("&Pattern Sequence Mode", self._projector_pattern_mode)
        projector_menu.addAction("&Stop Sequence", self._projector_stop_sequence)

    def _refresh_devices(self):
        self._device_menu.clear()
        self._available_cameras = enumerate_cameras()
        if not self._available_cameras:
            action = self._device_menu.addAction("No cameras found")
            action.setEnabled(False)
            return
        for cam in self._available_cameras:
            label = f"[{cam['backend']}] {cam['name']}"
            action = self._device_menu.addAction(label)
            backend = cam["backend"]
            idx = cam["index"]
            action.triggered.connect(
                lambda checked, b=backend, i=idx: self._select_device(b, i)
            )

    def _select_device(self, backend: str, index: int):
        was_running = self._camera_thread is not None and self._camera_thread.isRunning()
        if was_running:
            self._stop_camera()
        self._create_camera_thread(backend, index)
        self.statusBar().showMessage(f"Selected {backend} camera {index}", 3000)
        if was_running:
            self._start_camera()

    def _create_camera_thread(self, backend: str, index: int):
        if self._camera_thread is not None:
            self._camera_thread.stop()
            self._camera_thread.deleteLater()
        if backend == "pyspin":
            self._camera_thread = PySpinCameraThread(device_index=index, parent=self)
        else:
            self._camera_thread = OpenCVCameraThread(device_index=index, parent=self)
        self._camera_thread.frame_ready.connect(self._camera_view.update_frame)
        self._camera_thread.frame_ready.connect(self._on_camera_frame)
        self._camera_thread.fps_updated.connect(self._on_fps_updated)
        self._camera_thread.error.connect(self._on_camera_error)

    # -- DLPC350 USB control (PRO4500) -------------------------------------

    def _projector_usb(self, action, success_msg: str):
        """Run a ProjectorController action with uniform error reporting."""
        ctl = self._projector_ctl
        if not ctl.available:
            self.statusBar().showMessage(
                "USB projector control unavailable - install: pip install -e .[hardware]",
                6000,
            )
            return False
        try:
            action()
        except Exception as exc:  # noqa: BLE001 - surface any pyusb/backend error
            self.statusBar().showMessage(f"Projector USB error: {exc}", 6000)
            return False
        self.statusBar().showMessage(success_msg, 4000)
        return True

    def _projector_connect(self):
        from microprojection.acquisition.projector import enumerate_projectors
        ctl = self._projector_ctl
        if not ctl.available:
            msg = "USB projector control unavailable - install: pip install -e .[hardware]"
            self.statusBar().showMessage(msg, 6000)
            self._projector_panel.set_status(msg)
            return
        devices = enumerate_projectors()
        self._projector_panel.set_devices(devices)
        if devices:
            msg = f"PRO4500 detected on USB (DLPC350) - {len(devices)} device(s)"
        else:
            msg = "No DLPC350 device found - check USB and libusb backend (Zadig)"
        self.statusBar().showMessage(msg, 5000)
        self._projector_panel.set_status(msg)

    def _projector_pattern_mode_panel(self, opts: dict):
        """Pattern-sequence mode from the panel (num_pats from the phase steps)."""
        n_steps = int(self._parameter_panel.get_params().get("n_steps", 4))
        self._projector_usb(
            lambda: self._projector_ctl.pattern_mode(
                num_pats=n_steps,
                fps=float(opts.get("fps", paper_specs.PROJECTOR_HDMI_GRAYSCALE_FPS)),
                bit_depth=int(opts.get("bit_depth", 8)),
                led_color=int(opts.get("led_color", 0b111)),
            ),
            f"Pattern mode: {n_steps} patterns @ {opts.get('fps')} Hz",
        )

    def _projector_power_up(self):
        self._projector_usb(self._projector_ctl.power_up, "Projector powered up")

    def _projector_power_down(self):
        self._projector_usb(self._projector_ctl.power_down, "Projector in standby")

    def _projector_pattern_mode(self):
        params = self._parameter_panel.get_params()
        n_steps = int(params.get("n_steps", 4))
        # 8-bit grayscale sinusoids stream at up to ~120 Hz over HDMI.
        fps = float(paper_specs.PROJECTOR_HDMI_GRAYSCALE_FPS)
        self._projector_usb(
            lambda: self._projector_ctl.pattern_mode(
                num_pats=n_steps, fps=fps, bit_depth=8, led_color=0b111
            ),
            f"Pattern sequence mode: {n_steps} patterns @ {fps:.0f} Hz",
        )

    def _projector_stop_sequence(self):
        self._projector_usb(self._projector_ctl.stop_sequence, "Pattern sequence stopped")

    # -- Pattern-sequence capture (USB) ------------------------------------

    def _on_camera_frame(self, frame):
        """Store the latest frame; forward to the live pipeline unless capturing."""
        self._latest_capture_frame = frame
        if not self._capturing:
            self._pipeline_thread.submit_frame(frame)

    @staticmethod
    def _to_gray(image: np.ndarray) -> np.ndarray:
        arr = np.asarray(image, dtype=np.float64)
        if arr.ndim == 3:
            return arr[..., :3].mean(axis=2)
        return arr

    def _on_capture_requested(self, opts: dict):
        """Engage the USB pattern sequence and collect one frame per phase step.

        The projector cycles its n patterns over USB; we collect n camera frames
        spaced by the configured interval and feed the stack to the N-step PSA
        pipeline. Per-pattern hardware sync (camera trigger-in <- projector
        trigger-out) is the future hardware path; this is the software-timed
        collection until that line is wired.
        """
        if self._capturing:
            return
        ctl = self._projector_ctl
        if not ctl.available:
            msg = ("USB projector control required for capture - "
                   "install: pip install -e .[hardware] and connect the PRO4500.")
            self.statusBar().showMessage(msg, 6000)
            self._projector_panel.set_status(msg)
            return
        if self._camera_thread is None or not self._camera_thread.isRunning():
            self.statusBar().showMessage(
                "Start the camera first (Camera > Start) before capturing.", 5000
            )
            self._projector_panel.set_status("Capture needs a running camera.")
            return
        n = int(self._parameter_panel.get_params().get("n_steps", 4))
        if n < 3:
            self.statusBar().showMessage("Need >= 3 phase steps to reconstruct.", 5000)
            return
        started = self._projector_usb(
            lambda: ctl.pattern_mode(
                num_pats=n,
                fps=float(opts.get("fps", paper_specs.PROJECTOR_HDMI_GRAYSCALE_FPS)),
                bit_depth=int(opts.get("bit_depth", 8)),
                led_color=int(opts.get("led_color", 0b111)),
            ),
            f"Pattern sequence started ({n} patterns)",
        )
        if not started:
            return

        self._capturing = True
        self._cap_frames = []
        self._cap_step = 0
        self._cap_n = n
        self._latest_capture_frame = None
        self._cap_wait_ticks = 0
        self._projector_panel.set_busy(True)
        self._projector_panel.set_status(f"Capturing {n} frames from the pattern sequence...")
        self._cap_timer.start(int(opts.get("settle_ms", 200)))

    def _on_capture_tick(self):
        if not self._capturing:
            self._cap_timer.stop()
            return
        frame = self._latest_capture_frame
        if frame is None:
            self._cap_wait_ticks += 1
            if self._cap_wait_ticks > 40:
                self._abort_capture("camera stopped delivering frames")
            return
        self._cap_frames.append(self._to_gray(frame.image))
        self._latest_capture_frame = None  # force a fresh frame for the next step
        self._cap_wait_ticks = 0
        self._cap_step += 1
        if self._cap_step >= self._cap_n:
            self._cap_timer.stop()
            self._finish_capture()

    def _stop_sequence_safe(self):
        if self._projector_ctl.available:
            try:
                self._projector_ctl.stop_sequence()
            except Exception:  # noqa: BLE001
                pass

    def _abort_capture(self, reason: str):
        self._cap_timer.stop()
        self._capturing = False
        self._stop_sequence_safe()
        self._projector_panel.set_busy(False)
        self.statusBar().showMessage(f"Capture aborted: {reason}", 6000)
        self._projector_panel.set_status(f"Capture aborted: {reason}")

    def _finish_capture(self):
        self._capturing = False
        self._stop_sequence_safe()
        self._projector_panel.set_busy(False)
        frames = self._cap_frames
        shapes = {f.shape for f in frames}
        if len(frames) < 3 or len(shapes) != 1:
            self._projector_panel.set_status(
                f"Capture failed: got {len(frames)} usable frames."
            )
            return
        stack = np.stack(frames, axis=0)  # (N, H, W) -> N-step PSA in the pipeline
        self._pipeline_thread.submit_frame(
            CaptureFrame(image=stack, timestamp=time.time())
        )
        msg = f"Captured {len(frames)} frames -> reconstructing"
        self.statusBar().showMessage(msg, 4000)
        self._projector_panel.set_status(msg)

    def _generate_fringe(self, params: dict) -> np.ndarray:
        """Reference sinusoidal fringe for the in-app preview (not projected)."""
        w, h = 640, 480
        period = params.get("period", 16.0)
        n_steps = params.get("n_steps", 4)
        step = params.get("current_step", 0)
        shift = 2 * np.pi * step / n_steps
        x = np.arange(w, dtype=np.float64)
        # sin-based fringe to match the simulation's convention; the PSA in
        # processing/steps.py returns +phi for sin fringes.
        pattern = 127.5 + 127.5 * np.sin(2 * np.pi * x / period + shift)
        pattern_2d = np.tile(pattern.astype(np.uint8), (h, 1))
        return pattern_2d

    def _update_fringe_pattern(self, params: dict = None):
        if params is None:
            params = self._parameter_panel.get_params()
        pattern = self._generate_fringe(params)
        self._projection_view.update_pattern(pattern)

    def _start_camera(self):
        if self._camera_thread is None:
            self.statusBar().showMessage("No camera selected - use Camera > Select Device", 5000)
            return
        self._update_fringe_pattern()
        if not self._camera_thread.isRunning():
            self._camera_thread.start()
        if not self._pipeline_thread.isRunning():
            self._pipeline_thread.start()
        self.statusBar().showMessage("Camera started", 3000)

    def _stop_camera(self):
        if self._capturing:
            self._abort_capture("camera stopped")
        if self._camera_thread is not None:
            self._camera_thread.stop()
        self._pipeline_thread.stop()
        self._fps_label.setText("FPS: --")
        self._pipeline_label.setText("Pipeline: idle")
        self.statusBar().showMessage("Camera stopped", 3000)

    def _on_fps_updated(self, fps: float):
        self._fps_label.setText(f"FPS: {fps:.1f}")

    def _on_camera_error(self, msg: str):
        self.statusBar().showMessage(f"Camera error: {msg}", 5000)

    def _on_pipeline_result(self, result):
        ms = result.processing_time * 1000
        self._pipeline_label.setText(f"Pipeline: {ms:.1f} ms")
        self._latest_result = result

    def _on_calibration_changed(self, params: dict):
        # Forward the calibrated lambda_eq / pixel pitch into the pipeline so
        # the height conversion + Gaussian S-filter use real-rig parameters.
        forwarded = {
            "lambda_eq": float(params.get("lambda_eq_mm", 0.32)),
            "filter_cutoff": float(15.0),  # default cutoff lambda_c in mm
            "pixel_pitch_mm": float(params.get("pixel_pitch_mm", 0.214)),
        }
        self._pipeline_thread.update_params(
            {**self._parameter_panel.get_params(), **forwarded}
        )
        self.statusBar().showMessage(
            f"Calibration applied: lambda_eq = {forwarded['lambda_eq']:.4f} mm", 5000
        )

    def _on_export_report(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        if self._latest_result is None:
            QMessageBox.information(self, "Export Report",
                                    "No measurement to export yet. Run an acquisition first.")
            return
        directory = QFileDialog.getExistingDirectory(self, "Choose report output directory")
        if not directory:
            return
        try:
            results_path = save_report(
                directory,
                self._latest_result,
                calibration=self._calibration_tab._calibrated or None,
                parameters=self._parameter_panel.get_params(),
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export Report", f"Failed to write report:\n{exc}")
            return
        QMessageBox.information(self, "Export Report",
                                f"Report saved to:\n{results_path}")

    def closeEvent(self, event):
        self._cap_timer.stop()
        self._capturing = False
        # Don't leave the projector stuck mid-sequence.
        if self._projector_ctl.available and self._projector_ctl.in_pattern_mode:
            self._stop_sequence_safe()
        if self._camera_thread is not None:
            self._camera_thread.stop()
        self._pipeline_thread.stop()
        super().closeEvent(event)
