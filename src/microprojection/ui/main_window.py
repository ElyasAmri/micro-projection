import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
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
from microprojection.export import save_report
from microprojection.processing.pipeline import PipelineThread
from microprojection.ui.calibration_tab import CalibrationTab
from microprojection.ui.camera_view import CameraView
from microprojection.ui.parameter_panel import ParameterPanel
from microprojection.ui.projection_view import ProjectionView
from microprojection.ui.projector_window import ProjectorWindow
from microprojection.ui.result_view import ResultView
from microprojection.ui.results_panel import ResultsPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MicroProjection - Fringe Projection Profilometry")
        self.resize(1280, 800)

        # -- Widgets --
        self._calibration_tab = CalibrationTab()
        self._projection_view = ProjectionView()
        self._camera_view = CameraView()
        self._result_view = ResultView()
        self._parameter_panel = ParameterPanel()
        self._results_panel = ResultsPanel()
        self._latest_result = None  # last PipelineResult, used by Export Report

        # -- Layout --
        # Left: top-level workflow tabs (in execution order: calibrate, project,
        # capture, reconstruct).
        self._tabs = QTabWidget()
        self._tabs.addTab(self._calibration_tab, "Calibration")
        self._tabs.addTab(self._projection_view, "Projected Fringe")
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

        # -- Projector --
        self._projector_window = None

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

        projector_menu = menu_bar.addMenu("&Projector")
        self._screen_menu = projector_menu.addMenu("Select &Screen")
        projector_menu.addSeparator()
        projector_menu.addAction("&Show", self._show_projector)
        projector_menu.addAction("&Hide", self._hide_projector)
        projector_menu.addSeparator()
        projector_menu.addAction("&Refresh Screens", self._refresh_screens)

        self._refresh_screens()

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
        self._camera_thread.frame_ready.connect(self._pipeline_thread.submit_frame)
        self._camera_thread.fps_updated.connect(self._on_fps_updated)
        self._camera_thread.error.connect(self._on_camera_error)

    def _refresh_screens(self):
        self._screen_menu.clear()
        screens = QApplication.screens()
        for i, screen in enumerate(screens):
            geo = screen.geometry()
            name = screen.name()
            label = f"{name} ({geo.width()}x{geo.height()})"
            # Mark the primary screen
            if screen == QApplication.primaryScreen():
                label += " [primary]"
            action = self._screen_menu.addAction(label)
            action.triggered.connect(
                lambda checked, s=screen: self._select_projector_screen(s)
            )

    def _select_projector_screen(self, screen):
        if self._projector_window is None:
            self._projector_window = ProjectorWindow()
        self._projector_window.move_to_screen(screen)
        self._update_fringe_pattern()
        self.statusBar().showMessage(f"Projector on {screen.name()}", 3000)

    def _show_projector(self):
        if self._projector_window is None:
            # Default to first non-primary screen, or primary if only one
            screens = QApplication.screens()
            target = None
            for s in screens:
                if s != QApplication.primaryScreen():
                    target = s
                    break
            if target is None:
                target = screens[0]
            self._select_projector_screen(target)
        else:
            self._projector_window.showFullScreen()
        self._update_fringe_pattern()

    def _hide_projector(self):
        if self._projector_window is not None:
            self._projector_window.hide()

    def _generate_fringe(self, params: dict) -> np.ndarray:
        """Generate a sinusoidal fringe pattern from current parameters."""
        if self._projector_window is not None and hasattr(self._projector_window, '_screen_size'):
            w, h = self._projector_window._screen_size
        else:
            w, h = 640, 480
        period = params.get("period", 16.0)
        n_steps = params.get("n_steps", 4)
        step = params.get("current_step", 0)
        shift = 2 * np.pi * step / n_steps
        x = np.arange(w, dtype=np.float64)
        pattern = 127.5 + 127.5 * np.cos(2 * np.pi * x / period + shift)
        pattern_2d = np.tile(pattern.astype(np.uint8), (h, 1))
        return pattern_2d

    def _update_fringe_pattern(self, params: dict = None):
        if params is None:
            params = self._parameter_panel.get_params()
        pattern = self._generate_fringe(params)
        self._projection_view.update_pattern(pattern)
        if self._projector_window is not None and self._projector_window.isVisible():
            self._projector_window.update_pattern(pattern)

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
        if self._projector_window is not None:
            self._projector_window.close()
        if self._camera_thread is not None:
            self._camera_thread.stop()
        self._pipeline_thread.stop()
        super().closeEvent(event)
