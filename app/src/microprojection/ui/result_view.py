import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from microprojection.core.datatypes import PipelineResult


def _ndarray_to_pixmap(arr: np.ndarray) -> QPixmap:
    """Convert a HxW float64 array to a grayscale QPixmap."""
    ptp = arr.ptp()
    if ptp > 0:
        norm = ((arr - arr.min()) / ptp * 255).astype(np.uint8)
    else:
        norm = np.zeros_like(arr, dtype=np.uint8)
    h, w = norm.shape
    norm_contiguous = np.ascontiguousarray(norm)
    qimg = QImage(norm_contiguous.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
    return QPixmap.fromImage(qimg)


class _ImageTab(QWidget):
    """Single tab showing a processed image."""

    def __init__(self, placeholder_text: str, parent=None):
        super().__init__(parent)
        self._label = QLabel(placeholder_text)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("QLabel { color: #888; font-size: 14px; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

    def update_image(self, arr: np.ndarray):
        pixmap = _ndarray_to_pixmap(arr)
        scaled = pixmap.scaled(
            self._label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)


class ResultView(QWidget):
    """Tabbed display for pipeline result images."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tabs = QTabWidget()

        self._phase_tab = _ImageTab("Run pipeline to see phase map")
        self._height_tab = _ImageTab("Run pipeline to see height map")
        self._roughness_tab = _ImageTab("Run pipeline to see filtered surface")

        self._tabs.addTab(self._phase_tab, "Phase")
        self._tabs.addTab(self._height_tab, "Height")
        self._tabs.addTab(self._roughness_tab, "Filtered")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tabs)

    def update_result(self, result: PipelineResult):
        self._phase_tab.update_image(result.phase_map)
        self._height_tab.update_image(result.height_map)
        self._roughness_tab.update_image(result.roughness_map)
