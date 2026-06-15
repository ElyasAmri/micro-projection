"""Modal live-camera preview.

A simple ``QDialog`` that renders frames from the active camera. MainWindow
connects ``CameraController.frameReady`` to ``update_frame`` while the dialog is
open and disconnects on close, so the preview only costs anything while shown.

Handles both frame shapes the cameras produce: RGB (HxWx3) from OpenCV and raw
mono (HxW) from PySpin, in 8- or 16-bit.
"""
from __future__ import annotations

import sys
from ctypes.wintypes import MSG, RECT

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

# WM_SIZING edge codes: which border/corner the user is dragging.
_WM_SIZING = 0x0214
_WMSZ_LEFT = 1
_WMSZ_RIGHT = 2
_WMSZ_TOP = 3
_WMSZ_TOPLEFT = 4
_WMSZ_TOPRIGHT = 5
_WMSZ_BOTTOM = 6
_WMSZ_BOTTOMLEFT = 7
_WMSZ_BOTTOMRIGHT = 8


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
        self._rescale()

    def nativeEvent(self, event_type, message):
        # Constrain the live resize rectangle to the frame aspect ratio. Doing
        # it here (before the resize happens) avoids the flicker that a resize()
        # inside resizeEvent causes when dragging a corner.
        if (
            self._aspect
            and sys.platform == "win32"
            and event_type == "windows_generic_MSG"
        ):
            msg = MSG.from_address(int(message))
            if msg.message == _WM_SIZING:
                self._constrain_sizing_rect(int(msg.wParam), int(msg.lParam))
                return True, 0
        return super().nativeEvent(event_type, message)

    def _constrain_sizing_rect(self, edge: int, rect_addr: int) -> None:
        rect = RECT.from_address(rect_addr)
        # The drag rect is the whole window; aspect applies to the content, so
        # subtract the non-client frame (title bar + borders).
        margin_w = self.frameGeometry().width() - self.geometry().width()
        margin_h = self.frameGeometry().height() - self.geometry().height()

        if edge in (_WMSZ_TOP, _WMSZ_BOTTOM):
            # vertical edge: width follows height, anchored at the left
            content_h = (rect.bottom - rect.top) - margin_h
            content_w = content_h * self._aspect
            rect.right = rect.left + round(content_w + margin_w)
        else:
            # horizontal/corner: height follows width
            content_w = (rect.right - rect.left) - margin_w
            content_h = content_w / self._aspect
            target_h = round(content_h + margin_h)
            if edge in (_WMSZ_TOPLEFT, _WMSZ_TOPRIGHT):
                # anchor the bottom edge
                rect.top = rect.bottom - target_h
            else:
                # anchor the top edge
                rect.bottom = rect.top + target_h

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
