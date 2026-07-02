"""A canvas: one empty viewport.

Deliberately blank for now (just the viewport background). It already exposes
`set_image()` so a tab can render a frame later without the shell changing
shape; until then it draws nothing but its background.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from microprojection.ui.styles import COLORS


class Canvas(QWidget):
    """An empty viewport. Draws a fit-to-window image once `set_image` is
    given one, otherwise just its background."""

    def __init__(self, object_name: str = "canvas", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(360, 240)
        self._pixmap: QPixmap | None = None

    def set_image(self, image: QImage | QPixmap | None) -> None:
        """Show an image (or clear it with None) and repaint."""
        if image is None:
            self._pixmap = None
        elif isinstance(image, QImage):
            self._pixmap = QPixmap.fromImage(image)
        else:
            self._pixmap = image
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        painter.fillRect(rect, QColor(COLORS["viewport"]))
        if self._pixmap is not None and not self._pixmap.isNull():
            self._draw_image(painter, rect)
        painter.end()

    def _draw_image(self, painter: QPainter, rect) -> None:
        scaled = self._pixmap.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = rect.left() + (rect.width() - scaled.width()) // 2
        y = rect.top() + (rect.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
