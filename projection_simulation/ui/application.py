from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, QTimer
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

from ..core.constants import SURFACE_CAMERA_SENSOR_HEIGHT_PX, SURFACE_CAMERA_SENSOR_WIDTH_PX
from ..scanning.scan_pipeline import ScanReconstruction
from .reconstruction_view import ReconstructionWindow
from .window import ProjectionWindow

RIGHT_PANEL_MIN_WIDTH = 420
SURFACE_CAMERA_ASPECT = SURFACE_CAMERA_SENSOR_WIDTH_PX / SURFACE_CAMERA_SENSOR_HEIGHT_PX
RECONSTRUCTION_ASPECT = 4.0 / 3.0


class AspectRatioLabel(QLabel):
    def __init__(self, aspect_ratio: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._aspect_ratio = aspect_ratio

    def hasHeightForWidth(self) -> bool:  # type: ignore[override]
        return True

    def heightForWidth(self, width: int) -> int:  # type: ignore[override]
        return max(1, int(round(width / self._aspect_ratio)))

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(RIGHT_PANEL_MIN_WIDTH, self.heightForWidth(RIGHT_PANEL_MIN_WIDTH))


class AspectRatioFrame(QFrame):
    def __init__(self, aspect_ratio: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._aspect_ratio = aspect_ratio

    def hasHeightForWidth(self) -> bool:  # type: ignore[override]
        return True

    def heightForWidth(self, width: int) -> int:  # type: ignore[override]
        return max(1, int(round(width / self._aspect_ratio)))

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(RIGHT_PANEL_MIN_WIDTH, self.heightForWidth(RIGHT_PANEL_MIN_WIDTH))


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

        root.addWidget(self.projection_view)
        root.addWidget(self._build_inspector_panel())
        root.setStretchFactor(0, 1)
        root.setStretchFactor(1, 0)
        root.setSizes([980, 460])

        self._surface_timer = QTimer(self)
        self._surface_timer.setInterval(250)
        self._surface_timer.timeout.connect(self._refresh_surface_camera)
        self._surface_timer.start()

    def set_reload_handler(self, handler: Callable[[], None] | None) -> None:
        self.projection_view.set_reload_handler(handler)

    def _build_inspector_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("inspectorPanel")
        panel.setMinimumWidth(RIGHT_PANEL_MIN_WIDTH)
        panel.setStyleSheet(
            "#inspectorPanel { background-color: #151922; border-left: 1px solid #2d3442; }"
            "QLabel { color: #E6EAF2; }"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        controls_title = QLabel("Controls", panel)
        controls_title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(controls_title)

        controls = self.projection_view._controls_frame
        controls.setParent(panel)
        controls.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        controls.setVisible(True)
        layout.addWidget(controls)

        surface_title = QLabel("Surface camera", panel)
        surface_title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(surface_title)

        self._surface_camera_label = AspectRatioLabel(SURFACE_CAMERA_ASPECT, panel)
        self._surface_camera_label.setObjectName("surfaceCameraPane")
        self._surface_camera_label.setMinimumSize(360, 203)
        self._surface_camera_label.setAlignment(Qt.AlignCenter)
        self._surface_camera_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._surface_camera_label.setStyleSheet(
            "#surfaceCameraPane { background-color: #080A0E; border: 1px solid #2d3442; }"
        )
        layout.addWidget(self._surface_camera_label, 1)

        reconstruction_title = QLabel("Reconstruction", panel)
        reconstruction_title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(reconstruction_title)

        self._reconstruction_container = AspectRatioFrame(RECONSTRUCTION_ASPECT, panel)
        self._reconstruction_container.setObjectName("reconstructionPane")
        self._reconstruction_container.setMinimumSize(360, 270)
        self._reconstruction_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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
        capture_width, capture_height = self._surface_camera_capture_size()
        image = self.projection_view.render_surface_camera_telecentric_capture(
            capture_width,
            capture_height,
        )
        pixmap = QPixmap.fromImage(image)
        self._surface_camera_label.setPixmap(
            pixmap.scaled(
                self._surface_camera_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def _surface_camera_capture_size(self) -> tuple[int, int]:
        width = max(2, self._surface_camera_label.width())
        height = max(2, self._surface_camera_label.height())
        if width / height > SURFACE_CAMERA_ASPECT:
            width = int(round(height * SURFACE_CAMERA_ASPECT))
        else:
            height = int(round(width / SURFACE_CAMERA_ASPECT))
        return (max(2, width), max(2, height))

    def set_reconstruction(self, reconstruction: ScanReconstruction) -> None:
        if self._reconstruction_view is not None:
            self._reconstruction_layout.removeWidget(self._reconstruction_view)
            self._reconstruction_view.stop_playback()
            self._reconstruction_view.deleteLater()
            self._reconstruction_view = None
        self._reconstruction_placeholder.setVisible(False)
        self._reconstruction_view = ReconstructionWindow(reconstruction, loop_frames=False)
        self._reconstruction_view.setMinimumSize(360, 270)
        self._reconstruction_view.setParent(self._reconstruction_container)
        self._reconstruction_layout.addWidget(self._reconstruction_view)
        self._reconstruction_view.show()

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        self._surface_timer.stop()
        self.projection_view.dispose_gpu_renderer()
        super().closeEvent(event)
