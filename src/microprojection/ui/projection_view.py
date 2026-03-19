import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class ProjectionView(QWidget):
    """Displays the fringe pattern being projected."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._label = QLabel("No pattern generated")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumSize(320, 240)
        self._label.setStyleSheet("QLabel { color: #888; font-size: 14px; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

    def update_pattern(self, pattern: np.ndarray):
        """Update with a HxW uint8 or HxWx3 uint8 pattern image."""
        if pattern.ndim == 2:
            h, w = pattern.shape
            qimg = QImage(
                np.ascontiguousarray(pattern).data, w, h, w,
                QImage.Format.Format_Grayscale8,
            ).copy()
        else:
            h, w, ch = pattern.shape
            qimg = QImage(
                pattern.data, w, h, ch * w, QImage.Format.Format_RGB888,
            ).copy()
        pixmap = QPixmap.fromImage(qimg)
        scaled = pixmap.scaled(
            self._label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)
