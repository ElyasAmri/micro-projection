"""Programmatically painted icons.

Qt ships no gear/settings icon in its standard pixmap set, and the project
avoids non-ASCII font glyphs, so we paint the gear as vector art. This also
keeps the repo free of binary image assets.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap


def gear_icon(size: int = 16, color: str = "#c8ccd4", teeth: int = 8) -> QIcon:
    """A settings gear, painted at the given pixel size."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))

    cx = cy = size / 2.0
    hub_r = size * 0.30
    tooth_r = size * 0.46
    tooth_w = size * 0.16
    # flat-topped teeth spoked around the hub
    painter.save()
    painter.translate(cx, cy)
    for i in range(teeth):
        painter.save()
        painter.rotate(i * 360.0 / teeth)
        painter.drawRect(QRectF(-tooth_w / 2.0, -tooth_r, tooth_w, tooth_r))
        painter.restore()
    painter.restore()
    painter.drawEllipse(QPointF(cx, cy), hub_r, hub_r)
    # punch the center hole so it reads as a gear, not a sun
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    hole_r = size * 0.12
    painter.drawEllipse(QPointF(cx, cy), hole_r, hole_r)
    painter.end()
    return QIcon(pix)
