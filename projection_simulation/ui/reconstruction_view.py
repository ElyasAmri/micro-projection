from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QCloseEvent, QMouseEvent, QPainter, QPen, QPolygonF, QWheelEvent
from PySide6.QtWidgets import QWidget

from ..scanning.scan_pipeline import ScanReconstruction


class ReconstructionWindow(QWidget):
    def __init__(
        self,
        reconstruction: ScanReconstruction,
        *,
        loop_frames: bool = False,
    ) -> None:
        super().__init__()
        self._reconstruction = reconstruction
        self._loop_frames = loop_frames
        self._yaw = math.radians(-38.0)
        self._pitch = math.radians(56.0)
        self._zoom = 1.0
        self._drag_pos: QPointF | None = None
        self._frame_index = 0
        self._frames = reconstruction.frames
        self.setWindowTitle("Reconstructed scan")
        self.resize(980, 720)
        self.setMinimumSize(640, 420)
        self.setFocusPolicy(Qt.StrongFocus)
        self._timer = QTimer(self)
        self._timer.setInterval(700)
        self._timer.timeout.connect(self._advance_frame)
        if len(self._frames) > 1:
            self._timer.start()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._drag_pos is not None:
            current = event.position()
            delta = current - self._drag_pos
            self._drag_pos = current
            self._yaw += delta.x() * 0.01
            self._pitch = max(math.radians(10.0), min(math.radians(82.0), self._pitch + delta.y() * 0.008))
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self._drag_pos = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # type: ignore[override]
        steps = event.angleDelta().y() / 120.0
        if steps:
            self._zoom = max(0.35, min(4.0, self._zoom * math.exp(steps * 0.12)))
            self.update()
        event.accept()

    def stop_playback(self) -> None:
        self._timer.stop()

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        self.stop_playback()
        super().closeEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(8, 10, 14))
        self._draw_title(painter)
        self._draw_mesh(painter)
        painter.end()

    def _advance_frame(self) -> None:
        if not self._frames:
            return
        last_index = len(self._frames) - 1
        next_index = self._frame_index + 1
        if next_index > last_index:
            if self._loop_frames:
                self._frame_index = 0
                self.update()
            else:
                self.stop_playback()
            return

        self._frame_index = next_index
        self.update()
        if not self._loop_frames and self._frame_index == last_index:
            self.stop_playback()

    def _draw_title(self, painter: QPainter) -> None:
        frame = self._current_frame()
        metrics = frame.metrics if frame is not None else self._reconstruction.metrics
        object_label = self._reconstruction.object_name.replace("_", " ").title()
        painter.setPen(QColor(230, 236, 246))
        painter.drawText(16, 24, f"Reconstructed object: {object_label}")
        painter.setPen(QColor(175, 190, 210))
        frame_label = f"Frame: {frame.label}" if frame is not None else "Frame: final"
        painter.drawText(
            16,
            46,
            frame_label,
        )
        painter.drawText(
            16,
            68,
            (
                f"Similarity: corr={metrics.correlation:.3f}, R2={metrics.r2:.3f}, "
                f"RMSE={metrics.rmse:.3f}, eval={metrics.count}"
            ),
        )
        painter.drawText(16, 90, "Left-drag to rotate, mouse wheel to zoom")

    def _draw_mesh(self, painter: QPainter) -> None:
        frame = self._current_frame()
        data = frame.height if frame is not None else self._reconstruction.height
        truth = self._reconstruction.truth
        mask = frame.mask if frame is not None else self._reconstruction.mask
        height, width = data.shape
        step = max(1, int(max(width, height) / 80))
        valid_values = data[mask & np.isfinite(data)]
        if valid_values.size == 0:
            return
        z_min = float(np.percentile(valid_values, 2.0))
        z_max = float(np.percentile(valid_values, 98.0))
        z_span = max(1e-6, z_max - z_min)
        scale = min(self.width() * 0.72 / max(1, width), self.height() * 0.72 / max(1, height)) * self._zoom
        center = QPointF(self.width() * 0.54, self.height() * 0.58)

        quads: list[tuple[float, QPolygonF, QColor]] = []
        for y in range(0, height - step, step):
            for x in range(0, width - step, step):
                cells = [(y, x), (y, x + step), (y + step, x + step), (y + step, x)]
                if not all(mask[cy, cx] and np.isfinite(data[cy, cx]) for cy, cx in cells):
                    continue
                points = [
                    self._project_point(cx, cy, data[cy, cx], width, height, scale, center)
                    for cy, cx in cells
                ]
                avg_depth = sum(point[0] for point in points) / len(points)
                polygon = QPolygonF([point[1] for point in points])
                value = float(np.mean([data[cy, cx] for cy, cx in cells]))
                truth_value = float(np.mean([truth[cy, cx] for cy, cx in cells if np.isfinite(truth[cy, cx])]))
                color = self._height_color(value, z_min, z_span)
                if np.isfinite(truth_value):
                    error = min(1.0, abs(value - truth_value) / max(0.25, z_span))
                    color = QColor(
                        min(255, int(color.red() + 90 * error)),
                        max(0, int(color.green() * (1.0 - 0.35 * error))),
                        max(0, int(color.blue() * (1.0 - 0.35 * error))),
                    )
                quads.append((avg_depth, polygon, color))

        quads.sort(key=lambda item: item[0], reverse=True)
        painter.setPen(QPen(QColor(25, 32, 44), 0.7))
        for _, polygon, color in quads:
            painter.setBrush(color)
            painter.drawPolygon(polygon)

    def _project_point(
        self,
        x: int,
        y: int,
        z: float,
        width: int,
        height: int,
        scale: float,
        center: QPointF,
    ) -> tuple[float, QPointF]:
        px = x - width * 0.5
        py = y - height * 0.5
        pz = z * max(width, height) * 0.20
        cy = math.cos(self._yaw)
        sy = math.sin(self._yaw)
        cp = math.cos(self._pitch)
        sp = math.sin(self._pitch)
        rx = px * cy - py * sy
        ry = px * sy + py * cy
        rz = pz
        screen_x = center.x() + rx * scale
        screen_y = center.y() + (ry * cp - rz * sp) * scale
        depth = ry * sp + rz * cp
        return depth, QPointF(screen_x, screen_y)

    @staticmethod
    def _height_color(value: float, z_min: float, z_span: float) -> QColor:
        t = max(0.0, min(1.0, (value - z_min) / z_span))
        return QColor(
            int(45 + 170 * t),
            int(95 + 115 * (1.0 - abs(t - 0.55))),
            int(185 - 120 * t),
        )

    def _current_frame(self):
        if not self._frames:
            return None
        return self._frames[self._frame_index]
