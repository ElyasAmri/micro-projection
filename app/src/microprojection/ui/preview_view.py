"""Live-camera preview embedded in the main viewport.

A plain widget that renders frames from the active camera, scaled to fit while
keeping aspect ratio. MainWindow keeps ``CameraController.frameReady`` connected
to ``update_frame`` for the life of the window; the camera only emits while
running, and ``clear`` resets to the placeholder when it stops.

``update_frame`` only stores the most recent frame; a timer renders it at a
capped rate and drops any frames that arrived in between. Rendering every frame
synchronously would let the GUI fall behind the camera and the latency grow
without bound (visible as preview lag), so the preview is deliberately decoupled
from the camera's frame rate.

Handles both frame shapes the cameras produce: RGB (HxWx3) from OpenCV and raw
mono (HxW) from PySpin, in 8- or 16-bit.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


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


class PreviewView(QWidget):
    """Embedded widget showing the live camera feed, scaled to fit."""

    _PLACEHOLDER = "No camera running"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #101216;")

        self._label = QLabel(self._PLACEHOLDER)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("color: #8a8f99;")
        self._label.setMinimumSize(320, 240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

        self._pixmap: QPixmap | None = None
        self._latest = None  # most recent frame awaiting render

        # Render at ~30 Hz from the latest frame only; intermediate frames are
        # dropped so a slow render never lets latency accumulate.
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._render_latest)
        self._timer.start()

    def update_frame(self, frame) -> None:
        # Cheap: just keep the newest frame; the timer does the actual render.
        self._latest = frame

    def _render_latest(self) -> None:
        if self._latest is None:
            return
        frame = self._latest
        self._latest = None
        image = _to_qimage(getattr(frame, "image", None))
        if image is None:
            return
        self._pixmap = QPixmap.fromImage(image)
        self._rescale()

    def clear(self) -> None:
        """Drop the current frame and show the placeholder (camera stopped)."""
        self._latest = None
        self._pixmap = None
        self._label.setText(self._PLACEHOLDER)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
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
