"""The projector, driven as a second screen.

A DLP projector connected over HDMI shows up to the OS as an ordinary display;
we project a fringe by putting a borderless, black-background fullscreen window
on it and painting the pattern into it (this is how the Windows rig did it, and
macOS exposes the external display the same way via QScreen). No projector SDK
is involved -- the "projector" is just a `QScreen`.

`ProjectorController` owns that window and picks the target screen: the first
non-primary display if one is attached, else it falls back to a small windowed
preview on the primary screen so the app is still usable while bench-testing
without a projector. Patterns are shown pixel-for-pixel (no smoothing) so the
sinusoid the camera images is exactly the one we generated.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from logbus import get_logger

log = get_logger("projector")


def pick_projector_screen(app: QApplication | None = None):
    """The screen to project onto: the first non-primary display, or None if
    only one screen is attached (bench-testing without a projector)."""
    app = app or QApplication.instance()
    if app is None:
        return None
    primary = app.primaryScreen()
    for screen in app.screens():
        if screen is not primary:
            return screen
    return None


def _to_qimage(pattern: np.ndarray) -> QImage:
    """An (H,W) uint8 grayscale (or (H,W,3) RGB) array to a QImage that owns
    its pixels."""
    arr = np.ascontiguousarray(pattern)
    if arr.ndim == 2:
        h, w = arr.shape
        return QImage(arr.tobytes(), w, h, w, QImage.Format_Grayscale8).copy()
    h, w, ch = arr.shape
    return QImage(arr.tobytes(), w, h, ch * w, QImage.Format_RGB888).copy()


class ProjectorWindow(QWidget):
    """A frameless, always-on-top, black window that fills a screen and paints
    the pattern into it. Esc hides it (so a fullscreen projection can be
    dismissed from the keyboard during a bench session)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Projector")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: black;")
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet("background-color: black;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

    @Slot(object)
    def show_pattern(self, pattern: np.ndarray) -> None:
        """Display an (H,W) uint8 (or RGB) pattern, scaled to fill the window
        with no smoothing (nearest-neighbour), so a full-screen sinusoid stays a
        sinusoid rather than being blurred by interpolation."""
        pixmap = QPixmap.fromImage(_to_qimage(pattern))
        target = self._label.size()
        if target.width() > 0 and target.height() > 0:
            pixmap = pixmap.scaled(
                target, Qt.IgnoreAspectRatio, Qt.FastTransformation
            )
        self._label.setPixmap(pixmap)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)


class ProjectorController:
    """Owns the projector window and where it lives. Lazily creates the window
    on first use, targeting the external display if present."""

    def __init__(self) -> None:
        self._window: ProjectorWindow | None = None
        self._windowed = False  # True when falling back to a primary-screen preview

    # -- lifecycle -----------------------------------------------------------

    def ensure_shown(self) -> ProjectorWindow:
        """Create + show the projector window (fullscreen on the external
        display, or a windowed preview if there's only one screen)."""
        if self._window is None:
            self._window = ProjectorWindow()
        window = self._window
        screen = pick_projector_screen()
        if screen is not None:
            window.setScreen(screen)
            window.setGeometry(screen.geometry())
            window.showFullScreen()
            self._windowed = False
            log.info(f"projecting on external display '{screen.name()}' "
                     f"({screen.geometry().width()}x{screen.geometry().height()})")
        elif not window.isVisible():
            # No second display: a modest preview window so bench work is possible.
            window.resize(570, 456)
            window.show()
            self._windowed = True
            log.warning("no external display found; projecting to a preview window "
                        "(connect the projector as a second screen for real use)")
        window.raise_()
        return window

    def screen_size(self) -> tuple[int, int]:
        """The projected surface's pixel size -- generate patterns at this size
        so they map 1:1 onto the projector."""
        screen = pick_projector_screen()
        if screen is not None:
            geo = screen.geometry()
            return geo.width(), geo.height()
        if self._window is not None and self._window.isVisible():
            return self._window.width(), self._window.height()
        return 1140, 912  # PRO4500 native, as a sane default before the window exists

    @property
    def window(self) -> ProjectorWindow:
        return self.ensure_shown()

    def show(self, pattern: np.ndarray) -> None:
        """Show one pattern (used by the live 'Project Fringe' button)."""
        self.ensure_shown().show_pattern(pattern)

    def close(self) -> None:
        if self._window is not None:
            self._window.close()
            self._window = None
