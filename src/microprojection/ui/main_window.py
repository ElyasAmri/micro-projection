from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from microprojection.acquisition.camera import CameraThread, enumerate_cameras
from microprojection.processing.pipeline import PipelineThread
from microprojection.ui.camera_view import CameraView
from microprojection.ui.parameter_panel import ParameterPanel
from microprojection.ui.result_view import ResultView
from microprojection.ui.results_panel import ResultsPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MicroProjection — Fringe Projection Profilometry")
        self.resize(1280, 800)

        # -- Widgets --
        self._camera_view = CameraView()
        self._result_view = ResultView()
        self._parameter_panel = ParameterPanel()
        self._results_panel = ResultsPanel()

        # -- Layout --
        # Left: camera (top) + results (bottom)
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.addWidget(self._camera_view)
        left_splitter.addWidget(self._result_view)
        left_splitter.setStretchFactor(0, 3)
        left_splitter.setStretchFactor(1, 2)

        # Right: parameters (top) + roughness (bottom)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self._parameter_panel, stretch=3)
        right_layout.addWidget(self._results_panel, stretch=1)

        # Outer: left + right
        outer_splitter = QSplitter(Qt.Orientation.Horizontal)
        outer_splitter.addWidget(left_splitter)
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
        self._camera_thread = CameraThread(device_index=0, parent=self)
        self._pipeline_thread = PipelineThread(parent=self)

        # -- Signals --
        self._camera_thread.frame_ready.connect(self._camera_view.update_frame)
        self._camera_thread.frame_ready.connect(self._pipeline_thread.submit_frame)
        self._camera_thread.fps_updated.connect(self._on_fps_updated)
        self._camera_thread.error.connect(self._on_camera_error)

        self._pipeline_thread.result_ready.connect(self._result_view.update_result)
        self._pipeline_thread.result_ready.connect(self._results_panel.update_roughness)
        self._pipeline_thread.result_ready.connect(self._on_pipeline_result)

        self._parameter_panel.parameters_changed.connect(
            self._pipeline_thread.update_params
        )

        # -- Menu bar --
        self._build_menus()

        # Send initial parameters
        self._pipeline_thread.update_params(self._parameter_panel.get_params())

    def _build_menus(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction("&Quit", self.close)

        camera_menu = menu_bar.addMenu("&Camera")
        self._device_menu = camera_menu.addMenu("Select &Device")
        camera_menu.addSeparator()
        camera_menu.addAction("&Start", self._start_camera)
        camera_menu.addAction("S&top", self._stop_camera)
        camera_menu.addSeparator()
        camera_menu.addAction("&Refresh Devices", self._refresh_devices)

        self._refresh_devices()

    def _refresh_devices(self):
        self._device_menu.clear()
        cameras = enumerate_cameras()
        if not cameras:
            action = self._device_menu.addAction("No cameras found")
            action.setEnabled(False)
            return
        for cam in cameras:
            action = self._device_menu.addAction(cam["name"])
            idx = cam["index"]
            action.triggered.connect(lambda checked, i=idx: self._select_device(i))

    def _select_device(self, index: int):
        was_running = self._camera_thread.isRunning()
        if was_running:
            self._stop_camera()
        self._camera_thread.device_index = index
        self.statusBar().showMessage(f"Selected camera {index}", 3000)
        if was_running:
            self._start_camera()

    def _start_camera(self):
        if not self._camera_thread.isRunning():
            self._camera_thread.start()
        if not self._pipeline_thread.isRunning():
            self._pipeline_thread.start()
        self.statusBar().showMessage("Camera started", 3000)

    def _stop_camera(self):
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

    def closeEvent(self, event):
        self._camera_thread.stop()
        self._pipeline_thread.stop()
        super().closeEvent(event)
