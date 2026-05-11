from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainter, QPen

from ..core.types import Vec3


class GridRenderingMixin:
    def _draw_ground_grid(
        self, painter: QPainter, viewport_width: int, viewport_height: int
    ) -> None:
        context = self._camera_projection_context(viewport_width, viewport_height)
        if context is None:
            return
        steps = int(self.grid_extent / self.grid_step)
        if steps <= 0:
            return

        minor_pen = QPen(QColor(55, 55, 55), 1)
        major_pen = QPen(QColor(95, 95, 95), 1)
        axis_pen = QPen(QColor(150, 150, 150), 2)

        def draw_segment(a: Vec3, b: Vec3, pen: QPen) -> None:
            projected_segment = self._project_segment_clipped(a, b, context)
            if projected_segment is None:
                return
            pa, pb = projected_segment
            painter.setPen(pen)
            painter.drawLine(pa, pb)

        for i in range(-steps, steps + 1):
            coord = i * self.grid_step
            pen = minor_pen
            if i == 0:
                pen = axis_pen
            elif i % self.grid_major_every == 0:
                pen = major_pen

            draw_segment(
                (coord, -self.grid_extent, 0.0),
                (coord, self.grid_extent, 0.0),
                pen,
            )
            draw_segment(
                (-self.grid_extent, coord, 0.0),
                (self.grid_extent, coord, 0.0),
                pen,
            )

        axis_length = min(self.grid_extent * 0.35, max(self.grid_step * 3.0, 6.0))
        x_axis_segment = self._project_segment_clipped(
            (0.0, 0.0, 0.0), (axis_length, 0.0, 0.0), context
        )
        if x_axis_segment is not None:
            painter.setPen(QPen(QColor(235, 70, 70), 2.5))
            pa, pb = x_axis_segment
            painter.drawLine(pa, pb)
        y_axis_segment = self._project_segment_clipped(
            (0.0, 0.0, 0.0), (0.0, axis_length, 0.0), context
        )
        if y_axis_segment is not None:
            painter.setPen(QPen(QColor(80, 220, 90), 2.5))
            pa, pb = y_axis_segment
            painter.drawLine(pa, pb)

        painter.save()
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        def format_marker(value: float) -> str:
            if abs(value) <= 1e-9:
                return "0"
            rounded = round(value)
            if abs(value - rounded) <= 1e-9:
                return str(int(rounded))
            return f"{value:.1f}".rstrip("0").rstrip(".")

        def draw_marker(candidates: list[Vec3], text: str, offset: QPointF) -> None:
            for world_point in candidates:
                screen_point = self._project_world_point(world_point, context)
                if screen_point is None:
                    continue
                painter.setPen(QColor(0, 0, 0, 220))
                painter.drawText(screen_point + offset + QPointF(1.0, 1.0), text)
                painter.setPen(QColor(190, 190, 190))
                painter.drawText(screen_point + offset, text)
                return

        for i in range(-steps, steps + 1):
            if i != 0 and i % self.grid_major_every != 0:
                continue
            coord = i * self.grid_step
            label = format_marker(coord)
            draw_marker(
                [
                    (coord, self.grid_extent, 0.0),
                    (coord, -self.grid_extent, 0.0),
                ],
                label,
                QPointF(4.0, -4.0),
            )
            draw_marker(
                [
                    (self.grid_extent, coord, 0.0),
                    (-self.grid_extent, coord, 0.0),
                ],
                label,
                QPointF(4.0, 12.0),
            )

        x_label_point = self._project_world_point((axis_length, 0.0, 0.0), context)
        if x_label_point is not None:
            painter.setPen(QColor(0, 0, 0, 220))
            painter.drawText(x_label_point + QPointF(7.0, -5.0), "X")
            painter.setPen(QColor(235, 70, 70))
            painter.drawText(x_label_point + QPointF(6.0, -6.0), "X")
        y_label_point = self._project_world_point((0.0, axis_length, 0.0), context)
        if y_label_point is not None:
            painter.setPen(QColor(0, 0, 0, 220))
            painter.drawText(y_label_point + QPointF(7.0, -5.0), "Y")
            painter.setPen(QColor(80, 220, 90))
            painter.drawText(y_label_point + QPointF(6.0, -6.0), "Y")
        painter.restore()
