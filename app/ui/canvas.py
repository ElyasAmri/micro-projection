"""A canvas: one empty viewport.

Deliberately blank for now (just the viewport background). It already exposes
`set_image()` so a tab can render a frame later without the shell changing
shape; until then it draws nothing but its background.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFontMetricsF,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from ui.styles import COLORS


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


class OrbitCanvas(Canvas):
    """A canvas whose viewpoint the user can orbit: dragging emits
    azimuth/elevation deltas ("grab the scene" -- the scene follows the hand),
    the scroll wheel emits a distance factor. It only reports intent; the owner
    re-renders and calls set_image, so motion lands one render later (the view
    is a Blender render, not a live viewport)."""

    orbited = Signal(float, float)  # d_azimuth_deg, d_elevation_deg
    zoomed = Signal(float)          # multiplicative distance factor
    released = Signal()             # drag ended -- time to render

    DEG_PER_PX = 0.35
    ZOOM_STEP = 1.1

    def __init__(self, object_name: str = "canvas", parent: QWidget | None = None) -> None:
        super().__init__(object_name, parent)
        self.setCursor(Qt.OpenHandCursor)
        self._grab_pos = None
        # View hint: what the next render will show (target) vs what the
        # displayed image shows (rendered) -- see set_view_hint.
        self._hint_target: dict | None = None
        self._hint_rendered: dict | None = None
        self._hint_rendering = False

    def set_view_hint(self, target: dict | None, rendered: dict | None,
                      rendering: bool) -> None:
        """Update the interaction gizmo: `target` is the orbit state the next
        render will use, `rendered` the state of the image on screen,
        `rendering` whether a render is in flight. The renders lag the mouse
        by seconds, so while the two differ a centered turntable gizmo tracks
        the drag live -- the image itself stays put until the render lands."""
        self._hint_target = dict(target) if target else None
        self._hint_rendered = dict(rendered) if rendered else None
        self._hint_rendering = bool(rendering)
        self.update()

    @staticmethod
    def _az_delta(target_deg: float, rendered_deg: float) -> float:
        """Signed shortest way around from rendered to target azimuth."""
        return (target_deg - rendered_deg + 180.0) % 360.0 - 180.0

    def _hint_active(self) -> bool:
        if self._hint_target is None or self._hint_rendered is None:
            return False
        if self._grab_pos is not None or self._hint_rendering:
            return True
        t, r = self._hint_target, self._hint_rendered
        return (abs(self._az_delta(t["azimuth"], r["azimuth"])) >= 0.5
                or abs(t["elevation"] - r["elevation"]) >= 0.5
                or abs(t["distance"] - r["distance"]) >= 0.005)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._grab_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._grab_pos is None:
            return
        pos = event.position()
        dx = pos.x() - self._grab_pos.x()
        dy = pos.y() - self._grab_pos.y()
        self._grab_pos = pos
        # Drag right -> scene spins right (camera orbits clockwise from above);
        # drag up -> view from higher (Qt y grows downward, hence both minuses).
        self.orbited.emit(-dx * self.DEG_PER_PX, -dy * self.DEG_PER_PX)

    def is_orbiting(self) -> bool:
        """True while a drag is in progress (between press and release)."""
        return self._grab_pos is not None

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._grab_pos = None
            self.setCursor(Qt.OpenHandCursor)
            self.released.emit()

    def wheelEvent(self, event) -> None:
        steps = event.angleDelta().y() / 120.0  # standard wheel notch
        if steps:
            self.zoomed.emit(self.ZOOM_STEP ** -steps)  # scroll up -> closer

    # -- the rotation gizmo ------------------------------------------------------

    @staticmethod
    def _camera_basis(azimuth_deg: float, elevation_deg: float):
        """The screen-space basis of an orbit camera at (azimuth, elevation)
        looking at the center: (right, up) world-space unit vectors. A world
        point projects orthographically to (dot(p, right), -dot(p, up))."""
        az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
        right = (-math.sin(az), math.cos(az), 0.0)
        up = (-math.sin(el) * math.cos(az), -math.sin(el) * math.sin(az), math.cos(el))
        return right, up

    def paintEvent(self, event) -> None:
        super().paintEvent(event)  # bg + image (never moved by interaction)
        if not self._hint_active():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._draw_gizmo(painter)
        painter.end()

    def _draw_gizmo(self, painter: QPainter) -> None:
        """Centered turntable gizmo tracking the drag live: the scene's ground
        ring and axes projected as the *target* camera will see them, plus a
        ghost of the on-screen render's orientation -- the gap between ghost
        and solid is the queued rotation. Numbers spelled out underneath."""
        t, r = self._hint_target, self._hint_rendered
        d_az = self._az_delta(t["azimuth"], r["azimuth"])
        d_el = t["elevation"] - r["elevation"]
        zoom = r["distance"] / t["distance"] if t["distance"] else 1.0

        radius = 76.0
        center = QPointF(self.width() / 2, self.height() / 2)

        def project(p, basis) -> QPointF:
            right, up = basis
            sx = p[0] * right[0] + p[1] * right[1] + p[2] * right[2]
            sy = p[0] * up[0] + p[1] * up[1] + p[2] * up[2]
            return QPointF(center.x() + radius * sx, center.y() - radius * sy)

        target = self._camera_basis(t["azimuth"], t["elevation"])
        ghost = self._camera_basis(r["azimuth"], r["elevation"])

        # Backdrop disc so the wireframe reads over any image content.
        bg = QColor(COLORS["viewport"])
        bg.setAlphaF(0.78)
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        painter.drawEllipse(center, radius + 18, radius + 18)
        painter.setBrush(Qt.NoBrush)

        accent = QColor(COLORS["accent"])
        dim = QColor(COLORS["text_dim"])
        faint = QColor(COLORS["text_faint"])

        def ring(basis, color, width) -> None:
            points = QPolygonF()
            for i in range(49):
                a = 2.0 * math.pi * i / 48
                points.append(project((math.cos(a), math.sin(a), 0.0), basis))
            painter.setPen(QPen(color, width))
            painter.drawPolyline(points)

        def axis(p, basis, color, width, dot_r=2.5) -> None:
            tip = project(p, basis)
            painter.setPen(QPen(color, width))
            painter.drawLine(center, tip)
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(tip, dot_r, dot_r)
            painter.setBrush(Qt.NoBrush)

        # Ghost first (the orientation of the image on screen)...
        axis((1.0, 0.0, 0.0), ghost, faint, 2.0, 2.5)
        axis((0.0, 0.0, 0.9), ghost, faint, 2.0, 2.5)
        # ...then the live target orientation on top.
        ring(target, dim, 1.8)
        axis((0.0, 1.0, 0.0), target, dim, 2.0)
        axis((1.0, 0.0, 0.0), target, accent, 3.0, 3.5)   # the handle that spins
        axis((0.0, 0.0, 0.9), target, QColor(COLORS["text"]), 3.0, 3.5)  # world up

        # The queued rotation, in words, beneath the gizmo.
        parts = []
        if abs(d_az) >= 0.5:
            parts.append(f"rotate {d_az:+.0f}°")
        if abs(d_el) >= 0.5:
            parts.append(f"tilt {d_el:+.0f}°")
        if abs(zoom - 1.0) >= 0.01:
            parts.append(f"zoom ×{zoom:.2f}")
        if self._hint_rendering:
            parts.append("rendering…")
        elif self.is_orbiting():
            parts.append("release to render")
        else:
            parts.append("waiting")
        text = "   ".join(parts)

        font = painter.font()
        font.setPointSizeF(11.0)
        painter.setFont(font)
        metrics = QFontMetricsF(painter.font())
        pad_x, pad_y = 12.0, 5.0
        w = metrics.horizontalAdvance(text) + 2 * pad_x
        h = metrics.height() + 2 * pad_y
        pill_top = center.y() + radius + 24
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(QRectF(center.x() - w / 2, pill_top, w, h), h / 2, h / 2)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QColor(COLORS["text"]))
        painter.drawText(QPointF(center.x() - w / 2 + pad_x,
                                 pill_top + pad_y + metrics.ascent()), text)
