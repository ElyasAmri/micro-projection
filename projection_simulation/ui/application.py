from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..scanning.scan_pipeline import ScanReconstruction
from .reconstruction_view import ReconstructionWindow
from .window import ProjectionWindow


class ProjectionApplicationWindow(QMainWindow):
    def __init__(self, projection_view: ProjectionWindow) -> None:
        super().__init__()
        self.projection_view = projection_view
        self._reconstruction_view: ReconstructionWindow | None = None

        self.setWindowTitle("Projection Simulation")
        self.projection_view.set_surface_camera_minimap_visible(False)
        self.projection_view.set_reconstruction_handler(self.set_reconstruction)

        root = QSplitter(Qt.Horizontal, self)
        root.setChildrenCollapsible(False)
        self.setCentralWidget(root)

        sidebar = self._build_sidebar()
        root.addWidget(sidebar)
        root.addWidget(self.projection_view)
        root.addWidget(self._build_observation_panel())
        root.setStretchFactor(0, 0)
        root.setStretchFactor(1, 1)
        root.setStretchFactor(2, 0)
        root.setSizes([300, 980, 420])

        self._surface_timer = QTimer(self)
        self._surface_timer.setInterval(250)
        self._surface_timer.timeout.connect(self._refresh_surface_camera)
        self._surface_timer.start()

    def set_reload_handler(self, handler: Callable[[], None] | None) -> None:
        self.projection_view.set_reload_handler(handler)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame(self)
        sidebar.setObjectName("controlsSidebar")
        sidebar.setMinimumWidth(280)
        sidebar.setMaximumWidth(360)
        sidebar.setStyleSheet(
            "#controlsSidebar { background-color: #151922; border-right: 1px solid #2d3442; }"
            "QLabel { color: #E6EAF2; }"
        )
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        title = QLabel("Controls", sidebar)
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)

        controls = self.projection_view._controls_frame
        controls.setParent(sidebar)
        controls.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        controls.setVisible(True)
        layout.addWidget(controls)
        layout.addStretch(1)
        return sidebar

    def _build_observation_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("observationPanel")
        panel.setMinimumWidth(340)
        panel.setStyleSheet(
            "#observationPanel { background-color: #10141C; border-left: 1px solid #2d3442; }"
            "QLabel { color: #E6EAF2; }"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        surface_title = QLabel("Surface camera", panel)
        surface_title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(surface_title)

        self._surface_camera_label = QLabel(panel)
        self._surface_camera_label.setObjectName("surfaceCameraPane")
        self._surface_camera_label.setMinimumSize(300, 180)
        self._surface_camera_label.setAlignment(Qt.AlignCenter)
        self._surface_camera_label.setStyleSheet(
            "#surfaceCameraPane { background-color: #080A0E; border: 1px solid #2d3442; }"
        )
        layout.addWidget(self._surface_camera_label, 1)

        reconstruction_title = QLabel("Reconstruction", panel)
        reconstruction_title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(reconstruction_title)

        self._reconstruction_container = QFrame(panel)
        self._reconstruction_container.setObjectName("reconstructionPane")
        self._reconstruction_container.setStyleSheet(
            "#reconstructionPane { background-color: #080A0E; border: 1px solid #2d3442; }"
        )
        self._reconstruction_layout = QVBoxLayout(self._reconstruction_container)
        self._reconstruction_layout.setContentsMargins(0, 0, 0, 0)
        self._reconstruction_placeholder = QLabel(
            "Run Scan and reconstruct to populate this pane.",
            self._reconstruction_container,
        )
        self._reconstruction_placeholder.setAlignment(Qt.AlignCenter)
        self._reconstruction_layout.addWidget(self._reconstruction_placeholder)
        layout.addWidget(self._reconstruction_container, 2)
        return panel

    def _refresh_surface_camera(self) -> None:
        if self._surface_camera_label.width() <= 2 or self._surface_camera_label.height() <= 2:
            return
        image = self.projection_view.render_surface_camera_telecentric_capture(
            self._surface_camera_label.width(),
            self._surface_camera_label.height(),
        )
        pixmap = QPixmap.fromImage(image)
        self._surface_camera_label.setPixmap(
            pixmap.scaled(
                self._surface_camera_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def set_reconstruction(self, reconstruction: ScanReconstruction) -> None:
        if self._reconstruction_view is not None:
            self._reconstruction_layout.removeWidget(self._reconstruction_view)
            self._reconstruction_view.stop_playback()
            self._reconstruction_view.deleteLater()
            self._reconstruction_view = None
        self._reconstruction_placeholder.setVisible(False)
        self._reconstruction_view = ReconstructionWindow(reconstruction, loop_frames=False)
        self._reconstruction_view.setParent(self._reconstruction_container)
        self._reconstruction_layout.addWidget(self._reconstruction_view)
        self._reconstruction_view.show()

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        self._surface_timer.stop()
        self.projection_view.dispose_gpu_renderer()
        super().closeEvent(event)
