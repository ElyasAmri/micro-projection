"""Live-camera preview embedded in the main viewport.

A plain widget that renders frames from the active camera, scaled to fit while
keeping aspect ratio. The preview is *pull-based*: a timer ticks at a capped
rate and asks ``frame_source()`` for the camera's most recent frame, rendering
whatever it gets and ignoring everything in between. ``clear`` resets to the
placeholder when the camera stops.

Pulling (rather than receiving a queued ``frameReady`` signal per frame) is what
keeps latency bounded. A per-frame cross-thread signal posts one event per
captured frame into the GUI event queue; if rendering can't keep pace those
events accumulate and the displayed image falls further and further behind the
camera (the preview-lag bug). With a pull, the camera only ever holds its single
newest frame and old frames are simply overwritten, never queued.

Handles both frame shapes the cameras produce: RGB (HxWx3) from OpenCV and raw
mono (HxW) from PySpin, in 8- or 16-bit.

``set_crosshair`` overlays a centered alignment reticle (the same cross plus
reference box as the projected crosshair pattern) on the live preview.
"""
from __future__ import annotations

import time

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
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

    def __init__(self, frame_source=None, parent=None):
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
        # Callable returning the camera's most recent CaptureFrame (or None).
        self._frame_source = frame_source
        # When set, a centered alignment crosshair is drawn over the preview.
        self._crosshair = False
        # TEMP PROBE: count renders to throttle the grab->display age log.
        self._probe_n = 0

        # Render at ~30 Hz, pulling only the newest frame each tick; anything
        # captured in between is overwritten at the source, never queued, so a
        # slow render can never let latency accumulate.
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._render_latest)
        self._timer.start()

    def set_source(self, frame_source) -> None:
        """Set the callable the timer pulls frames from."""
        self._frame_source = frame_source

    def set_crosshair(self, enabled: bool) -> None:
        """Toggle a centered alignment crosshair over the live preview, and
        repaint at once so it appears/clears without waiting for a new frame."""
        self._crosshair = bool(enabled)
        self._rescale()

    def _render_latest(self) -> None:
        if self._frame_source is None:
            return
        frame = self._frame_source()
        if frame is None:
            return
        # TEMP PROBE: grab->display age (GUI-side latency), ~once per second.
        self._probe_n += 1
        ts = getattr(frame, "timestamp", None)
        if ts is not None and self._probe_n % 30 == 0:
            print(f"[probe-gui] display_age={(time.time() - ts) * 1000:.0f} ms",
                  flush=True)
        image = _to_qimage(getattr(frame, "image", None))
        if image is None:
            return
        self._pixmap = QPixmap.fromImage(image)
        self._rescale()

    def clear(self) -> None:
        """Show the placeholder (camera stopped). The source then returns None,
        so the timer leaves the placeholder in place."""
        self._pixmap = None
        self._label.setText(self._PLACEHOLDER)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self) -> None:
        if self._pixmap is None:
            return
        scaled = self._pixmap.scaled(
            self._label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if self._crosshair:
            self._overlay_crosshair(scaled)
        self._label.setPixmap(scaled)

    def _overlay_crosshair(self, pix: QPixmap) -> None:
        """Draw a centered cross plus a reference box on the scaled image, the
        same reticle as the projected crosshair pattern, for optical-axis
        alignment. Drawn in display space so it stays centered on the frame."""
        painter = QPainter(pix)
        painter.setPen(QPen(QColor(0, 230, 0, 180), 1))
        w, h = pix.width(), pix.height()
        cx, cy = w // 2, h // 2
        painter.drawLine(0, cy, w, cy)
        painter.drawLine(cx, 0, cx, h)
        box = min(w, h) // 8
        painter.drawRect(cx - box, cy - box, 2 * box, 2 * box)
        painter.end()
