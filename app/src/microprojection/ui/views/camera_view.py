import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from microprojection.core.datatypes import CaptureFrame


class CameraView(QWidget):
    """Displays the live camera feed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._label = QLabel("No Camera")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumSize(320, 240)
        self._label.setStyleSheet("QLabel { color: #888; font-size: 14px; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

    def update_frame(self, frame: CaptureFrame):
        img = frame.image
        if img.ndim == 2:
            h, w = img.shape
            img = np.ascontiguousarray(img)
            qimg = QImage(img.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
        else:
            h, w, ch = img.shape
            qimg = QImage(img.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(qimg)
        scaled = pixmap.scaled(
            self._label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)
