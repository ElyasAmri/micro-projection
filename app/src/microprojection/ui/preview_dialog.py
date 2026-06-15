"""Modal live-camera preview.

A simple ``QDialog`` that renders frames from the active camera. MainWindow
connects ``CameraController.frameReady`` to ``update_frame`` while the dialog is
open and disconnects on close, so the preview only costs anything while shown.

Handles both frame shapes the cameras produce: RGB (HxWx3) from OpenCV and raw
mono (HxW) from PySpin, in 8- or 16-bit.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout


def _to_qimage(arr) -> QImage | None:
    """Convert a camera ndarray to an 8-bit QImage, or None if unsupported."""
    if arr is None or arr.ndim not in (2, 3):
        return None

    # Collapse high bit depths down to 8-bit for display.
    if arr.dtype == np.uint16:
        arr = (arr >> 8).astype(np.uint8)
    elif arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)

    arr = np.ascontiguousarray(arr)
    h, w = arr.shape[:2]

    if arr.ndim == 2:  # grayscale / mono
        return QImage(arr.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
    if arr.shape[2] == 3:  # RGB
        return QImage(arr.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
    return None


class PreviewDialog(QDialog):
    """Modal window showing the live camera feed, scaled to fit."""

    # bounding box the window is sized to fit on the first frame
    _FIT_BOX = (960, 720)

    def __init__(self, parent=None, *, camera_running: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Camera preview")
        self.setModal(True)
        self.resize(800, 600)

        self._label = QLabel(
            "Waiting for frames..." if camera_running else "No camera running"
        )
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumSize(320, 240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

        self._pixmap: QPixmap | None = None
        self._aspect: float | None = None
        self._adjusting = False

    def update_frame(self, frame) -> None:
        image = _to_qimage(getattr(frame, "image", None))
        if image is None:
            return
        self._pixmap = QPixmap.fromImage(image)
        # lock the window to the frame's aspect ratio on the first frame
        if self._aspect is None:
            self._size_to_frame(image.width(), image.height())
        self._rescale()

    def _size_to_frame(self, frame_w: int, frame_h: int) -> None:
        if frame_w <= 0 or frame_h <= 0:
            return
        self._aspect = frame_w / frame_h
        box_w, box_h = self._FIT_BOX
        scale = min(box_w / frame_w, box_h / frame_h)
        self.resize(round(frame_w * scale), round(frame_h * scale))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # keep a fixed aspect ratio: height follows width
        if self._aspect and not self._adjusting:
            self._adjusting = True
            self.resize(self.width(), round(self.width() / self._aspect))
            self._adjusting = False
        self._rescale()

    def _rescale(self) -> None:
        if self._pixmap is None:
            return
        self._label.setPixmap(
            self._pixmap.scaled(
                self._label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
