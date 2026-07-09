import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class ProjectorWindow(QWidget):
    """Fullscreen borderless window for projecting fringe patterns onto a secondary display."""

    def __init__(self, screen=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setStyleSheet("background-color: black;")

        self._screen_size = (0, 0)
        self._screen = None
        # Projector-camera alignment correction, applied to every pattern before
        # it is shown: an affine warp (2x3) and a clip box (x0, y0, x1, y1) in
        # projector pixels. Set by the alignment pipeline; None = no correction.
        self._warp = None
        self._clip = None
        self._raw_pattern = None  # last pattern as given, before warp/clip
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

        if screen is not None:
            self.move_to_screen(screen)

    def move_to_screen(self, screen):
        """Position this window fullscreen on the given QScreen."""
        geo = screen.geometry()
        self.setGeometry(geo)
        self._screen_size = (geo.width(), geo.height())
        self._screen = screen
        self.showFullScreen()

    def target_size(self):
        """(width, height) of the screen this window is projecting onto."""
        return self._screen_size

    def refresh_hz(self) -> float:
        """Refresh rate of the projector's screen in Hz, or 0 if unknown.

        Used to snap the camera exposure to whole projector frames so the
        projector/camera beat that causes brightness flicker cancels out.
        """
        return float(self._screen.refreshRate()) if self._screen is not None else 0.0

    def set_image_file(self, path: str) -> bool:
        """Display an image file, fit to the screen keeping aspect. False if it
        could not be loaded."""
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return False
        self._label.setPixmap(
            pixmap.scaled(
                self._label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        return True

    def set_warp(self, matrix, clip_box=None):
        """Apply an affine warp and optional clip box to every projected pattern,
        for projector-camera alignment. ``matrix`` is a 2x3 affine (or None to
        clear); ``clip_box`` is (x0, y0, x1, y1) in projector pixels (or None).
        Re-renders the current pattern so the change is visible at once."""
        self._warp = None if matrix is None else np.asarray(matrix, dtype=np.float64)
        self._clip = clip_box
        if self._raw_pattern is not None:
            self.update_pattern(self._raw_pattern)

    def _corrected(self, pattern: np.ndarray) -> np.ndarray:
        """Apply the alignment warp then the clip box, if set."""
        if self._warp is None and self._clip is None:
            return pattern
        out = pattern
        if self._warp is not None:
            h, w = out.shape[:2]
            out = cv2.warpAffine(out, self._warp, (w, h), flags=cv2.INTER_LINEAR,
                                 borderValue=0)
        if self._clip is not None:
            x0, y0, x1, y1 = (int(v) for v in self._clip)
            clipped = np.zeros_like(out)
            clipped[y0:y1, x0:x1] = out[y0:y1, x0:x1]
            out = clipped
        return out

    def update_pattern(self, pattern: np.ndarray):
        """Display a HxW uint8 grayscale or HxWx3 uint8 RGB pattern."""
        # Keep the raw pattern so set_warp can re-render it without double-warping.
        self._raw_pattern = pattern
        pattern = self._corrected(pattern)
        if pattern.ndim == 2:
            h, w = pattern.shape
            data = np.ascontiguousarray(pattern)
            qimg = QImage(data.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
        else:
            h, w, ch = pattern.shape
            data = np.ascontiguousarray(pattern)
            qimg = QImage(data.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()

        pixmap = QPixmap.fromImage(qimg)
        # Scale to fill the projector screen
        scaled = pixmap.scaled(
            self._label.size(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self._label.setPixmap(scaled)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        super().keyPressEvent(event)
