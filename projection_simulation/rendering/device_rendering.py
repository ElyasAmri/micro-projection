from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF

from ..core.constants import SURFACE_CAMERA_REAR_LENS_DIAMETER_CM, TELECENTRIC_LENS_DIAMETER_CM
from ..core.math3d import vec_cross, vec_dot, vec_normalize, vec_subtract
from ..core.types import CameraContext, Vec3

# Physical holder/clamp dimensions in centimeters. These were previously implicit in window.py.
PROJECTOR_HOLDER_OUTER_SIZE_CM = 6.0
PROJECTOR_HOLDER_OUTER_HEIGHT_CM = 3.0
PROJECTOR_HOLDER_INNER_SIZE_CM = 4.2
PROJECTOR_HOLDER_INNER_DROP_CM = 0.8
PROJECTOR_HOLDER_HEIGHT_CM = PROJECTOR_HOLDER_OUTER_HEIGHT_CM
SURFACE_CLAMP_OUTER_CIRCLE_DIAMETER_CM = 5.6
SURFACE_CLAMP_INNER_CIRCLE_DIAMETER_CM = 3.6
SURFACE_CLAMP_TOTAL_HEIGHT_CM = 8.5
SURFACE_CLAMP_BOTTOM_RECT_HEIGHT_CM = 2.51
SURFACE_CLAMP_THICKNESS_CM = 1.0
SURFACE_CLAMP_CIRCLE_CENTER_HEIGHT_CM = 5.3


class DeviceRenderingMixin:
    def _draw_projector_contours(
        self,
        painter: QPainter,
        pixmap: QPixmap,
        viewport_width: int,
        viewport_height: int,
    ) -> None:
        self._projector_projection_hit_world = None
        self._projector_ray_origin_world = None
        self._clamp_projection_hit_world = None
        self._clamp_ray_origin_world = None
        self._surface_camera_lens_origin_world = None
        view_context = self._camera_projection_context(viewport_width, viewport_height)
        if view_context is None:
            return
        if pixmap.width() <= 0 or pixmap.height() <= 0:
            return

        contour_pen = QPen(QColor(255, 235, 110, 190), 1)
        painter.setPen(contour_pen)
        projector_axes = self._projector_axes()
        if projector_axes is None:
            return
        projector_context = self._projector_projection_context(pixmap.width(), pixmap.height())
        if projector_context is None:
            return
        lens_data = self._projector_lens_rectangle_world()
        if lens_data is None:
            return
        lens_corners_world, lens_center_world = lens_data
        self._projector_ray_origin_world = lens_center_world

        for i in range(len(lens_corners_world)):
            segment = self._project_segment_clipped(
                lens_corners_world[i],
                lens_corners_world[(i + 1) % len(lens_corners_world)],
                view_context,
            )
            if segment is None:
                continue
            pa, pb = segment
            painter.drawLine(pa, pb)

        scene_surfaces = self._scene_surfaces()
        if not scene_surfaces:
            return

        source_corners = [
            (0.0, 0.0),
            (float(pixmap.width()), 0.0),
            (float(pixmap.width()), float(pixmap.height())),
            (0.0, float(pixmap.height())),
        ]
        hit_world_points: list[Vec3] = []
        projection_points: list[QPointF] = []
        for sx, sy in source_corners:
            hit = self._first_projector_hit(
                sx,
                sy,
                pixmap.width(),
                pixmap.height(),
                projector_context,
                scene_surfaces,
            )
            if hit is None:
                continue
            hit_world = hit[1]
            projected = self._project_world_point(hit_world, view_context)
            if projected is None:
                continue
            hit_world_points.append(hit_world)
            projection_points.append(projected)

        if len(projection_points) == 4:
            projection_quad = QPolygonF(projection_points)
            painter.save()
            raw_pen = QPen(QColor(255, 235, 110, 120), 1)
            raw_pen.setStyle(Qt.DashLine)
            painter.setPen(raw_pen)
            for i in range(projection_quad.count()):
                pa = projection_quad.at(i)
                pb = projection_quad.at((i + 1) % projection_quad.count())
                painter.drawLine(pa, pb)
            painter.setPen(QColor(255, 235, 110, 150))
            painter.drawText(projection_quad.at(0) + QPointF(6.0, -6.0), "Raw projector frustum")
            painter.restore()
        for i, hit in enumerate(hit_world_points):
            lens_corner = lens_corners_world[i % len(lens_corners_world)]
            segment = self._project_segment_clipped(lens_corner, hit, view_context)
            if segment is None:
                continue
            pa, pb = segment
            painter.drawLine(pa, pb)

        center_hit = self._first_projector_hit(
            pixmap.width() * 0.5,
            pixmap.height() * 0.5,
            pixmap.width(),
            pixmap.height(),
            projector_context,
            scene_surfaces,
        )
        projector_hit = center_hit[1] if center_hit is not None else None
        if projector_hit is not None:
            center_line = self._project_segment_clipped(
                lens_center_world, projector_hit, view_context
            )
            if center_line is not None:
                painter.save()
                painter.setPen(QPen(QColor(255, 190, 90, 210), 1.5))
                pa, pb = center_line
                painter.drawLine(pa, pb)
                painter.restore()
        self._projector_projection_hit_world = projector_hit

        clamp_context = self._surface_camera_telecentric_scan_context(
            pixmap.width(),
            pixmap.height(),
        )
        if clamp_context is not None:
            lens_centers = self._surface_camera_lens_centers_world()
            if lens_centers is None:
                return
            clamp_origin, camera_lens_origin, _ = lens_centers
            self._clamp_ray_origin_world = clamp_origin
            self._surface_camera_lens_origin_world = camera_lens_origin
            clamp_right = clamp_context[1]
            clamp_up = clamp_context[2]
            clamp_corners_world = self._lens_plane_corners(
                clamp_origin,
                clamp_right,
                clamp_up,
                TELECENTRIC_LENS_DIAMETER_CM,
                TELECENTRIC_LENS_DIAMETER_CM,
            )
            camera_lens_corners_world = self._lens_plane_corners(
                camera_lens_origin,
                clamp_right,
                clamp_up,
                SURFACE_CAMERA_REAR_LENS_DIAMETER_CM,
                SURFACE_CAMERA_REAR_LENS_DIAMETER_CM,
            )
            painter.save()
            painter.setPen(QPen(QColor(92, 222, 255, 230), 1.4))
            for corners in (clamp_corners_world, camera_lens_corners_world):
                for i in range(len(corners)):
                    segment = self._project_segment_clipped(
                        corners[i],
                        corners[(i + 1) % len(corners)],
                        view_context,
                    )
                    if segment is None:
                        continue
                    pa, pb = segment
                    painter.drawLine(pa, pb)
            painter.setPen(QPen(QColor(115, 235, 255, 150), 1))
            for telecentric_corner, camera_corner in zip(
                clamp_corners_world,
                camera_lens_corners_world,
            ):
                segment = self._project_segment_clipped(
                    telecentric_corner,
                    camera_corner,
                    view_context,
                )
                if segment is None:
                    continue
                pa, pb = segment
                painter.drawLine(pa, pb)
            axis_segment = self._project_segment_clipped(
                camera_lens_origin,
                clamp_origin,
                view_context,
            )
            if axis_segment is not None:
                painter.setPen(QPen(QColor(155, 245, 255, 190), 1.4))
                pa, pb = axis_segment
                painter.drawLine(pa, pb)
            painter.restore()

            clamp_projection_points: list[QPointF] = []
            clamp_hit_world_points: list[Vec3] = []
            for sx, sy in source_corners:
                clamp_hit = self._first_telecentric_scan_hit(
                    sx,
                    sy,
                    pixmap.width(),
                    pixmap.height(),
                    clamp_context,
                    scene_surfaces,
                )
                if clamp_hit is None:
                    continue
                hit_world = clamp_hit[1]
                projected = self._project_world_point(hit_world, view_context)
                if projected is None:
                    continue
                clamp_hit_world_points.append(hit_world)
                clamp_projection_points.append(projected)

            if len(clamp_projection_points) == 4:
                clamp_quad = QPolygonF(clamp_projection_points)
                painter.save()
                fill_color = QColor(92, 222, 255, 48)
                painter.setBrush(fill_color)
                painter.setPen(QPen(QColor(92, 222, 255, 220), 1.6))
                painter.drawPolygon(clamp_quad)
                painter.setBrush(Qt.NoBrush)
                for i in range(clamp_quad.count()):
                    pa = clamp_quad.at(i)
                    pb = clamp_quad.at((i + 1) % clamp_quad.count())
                    painter.drawLine(pa, pb)
                painter.restore()

            for i, hit in enumerate(clamp_hit_world_points):
                clamp_corner = clamp_corners_world[i % len(clamp_corners_world)]
                segment = self._project_segment_clipped(clamp_corner, hit, view_context)
                if segment is None:
                    continue
                painter.save()
                painter.setPen(QPen(QColor(92, 222, 255, 160), 1))
                pa, pb = segment
                painter.drawLine(pa, pb)
                painter.restore()

            clamp_center_hit = self._first_telecentric_scan_hit(
                pixmap.width() * 0.5,
                pixmap.height() * 0.5,
                pixmap.width(),
                pixmap.height(),
                clamp_context,
                scene_surfaces,
            )
            clamp_hit = clamp_center_hit[1] if clamp_center_hit is not None else None
            self._clamp_projection_hit_world = clamp_hit
            if clamp_hit is not None:
                clamp_segment = self._project_segment_clipped(clamp_origin, clamp_hit, view_context)
                if clamp_segment is not None:
                    painter.save()
                    painter.setPen(QPen(QColor(92, 222, 255, 210), 1.5))
                    pa, pb = clamp_segment
                    painter.drawLine(pa, pb)
                    painter.restore()

        clamp_hit = self._clamp_projection_hit_world

        projector_hit_2d = (
            self._project_world_point(projector_hit, view_context)
            if projector_hit is not None
            else None
        )
        clamp_hit_2d = (
            self._project_world_point(clamp_hit, view_context)
            if clamp_hit is not None
            else None
        )
        projector_origin = getattr(self, "_projector_ray_origin_world", None)
        clamp_origin = self._clamp_ray_origin_world
        camera_lens_origin = getattr(self, "_surface_camera_lens_origin_world", None)
        projector_origin_2d = (
            self._project_world_point(projector_origin, view_context)
            if projector_origin is not None
            else None
        )
        clamp_origin_2d = (
            self._project_world_point(clamp_origin, view_context)
            if clamp_origin is not None
            else None
        )
        camera_lens_origin_2d = (
            self._project_world_point(camera_lens_origin, view_context)
            if camera_lens_origin is not None
            else None
        )

        def draw_hit_marker(point: QPointF, world: Vec3, color: QColor, label: str) -> None:
            coord_text = f"({world[0]:.2f}, {world[1]:.2f}, {world[2]:.2f})"
            painter.save()
            painter.setPen(QPen(QColor(0, 0, 0, 230), 1.0))
            fill = QColor(color)
            fill.setAlpha(235)
            painter.setBrush(fill)
            painter.drawEllipse(point, 3.6, 3.6)
            painter.setPen(QColor(0, 0, 0, 220))
            painter.drawText(point + QPointF(7.0, -5.0), label)
            painter.drawText(point + QPointF(7.0, 9.0), coord_text)
            painter.setPen(color)
            painter.drawText(point + QPointF(6.0, -6.0), label)
            painter.drawText(point + QPointF(6.0, 8.0), coord_text)
            painter.restore()

        if projector_hit_2d is not None and projector_hit is not None:
            draw_hit_marker(projector_hit_2d, projector_hit, QColor(255, 190, 90), "Proj hit")
        if clamp_hit_2d is not None and clamp_hit is not None:
            draw_hit_marker(clamp_hit_2d, clamp_hit, QColor(92, 222, 255), "Scan hit")
        if projector_origin_2d is not None and projector_origin is not None:
            draw_hit_marker(
                projector_origin_2d,
                projector_origin,
                QColor(255, 146, 56),
                "Proj origin",
            )
        if clamp_origin_2d is not None and clamp_origin is not None:
            draw_hit_marker(
                clamp_origin_2d,
                clamp_origin,
                QColor(56, 180, 255),
                "Telecentric lens",
            )
        if camera_lens_origin_2d is not None and camera_lens_origin is not None:
            draw_hit_marker(
                camera_lens_origin_2d,
                camera_lens_origin,
                QColor(92, 222, 255),
                "Camera lens",
            )

    def _projected_surface_quad(
        self,
        center: Vec3,
        width: float,
        height: float,
        viewport_width: int,
        viewport_height: int,
        *,
        context: CameraContext | None = None,
    ) -> QPolygonF | None:
        if width <= 0 or height <= 0:
            return None
        if context is None:
            context = self._camera_projection_context(viewport_width, viewport_height)
        if context is None:
            return None

        projected: list[QPointF] = []
        for world_point in self._surface_world_corners(center, width, height):
            projected_point = self._project_world_point(world_point, context)
            if projected_point is None:
                return None
            projected.append(projected_point)
        return QPolygonF(projected)

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
        x_axis_segment = self._project_segment_clipped((0.0, 0.0, 0.0), (axis_length, 0.0, 0.0), context)
        if x_axis_segment is not None:
            painter.setPen(QPen(QColor(235, 70, 70), 2.5))
            pa, pb = x_axis_segment
            painter.drawLine(pa, pb)
        y_axis_segment = self._project_segment_clipped((0.0, 0.0, 0.0), (0.0, axis_length, 0.0), context)
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

    def _draw_oriented_box(
        self,
        painter: QPainter,
        context: CameraContext,
        origin: Vec3,
        look_target: Vec3,
        box_color: QColor,
        label: str,
        *,
        solid: bool = False,
        ground_to_world: bool = False,
        ground_world_z: float = 0.0,
        width: float | None = None,
        height: float | None = None,
        depth: float | None = None,
    ) -> None:
        w = self.projector_width if width is None else width
        h = self.projector_height if height is None else height
        d = self.projector_depth if depth is None else depth
        forward = vec_normalize(vec_subtract(look_target, origin))
        if forward is None:
            return
        world_up: Vec3 = (0.0, 0.0, 1.0)
        if abs(vec_dot(forward, world_up)) > 0.98:
            world_up = (0.0, 1.0, 0.0)
        right = vec_normalize(vec_cross(world_up, forward))
        if right is None:
            return
        up = vec_cross(forward, right)
        local_y_offset = 0.0
        if ground_to_world:
            local_y_offset = self._ground_alignment_local_y_offset(
                origin,
                up,
                -h / 2.0,
                target_world_z=ground_world_z,
            )

        def local_to_world(lx: float, ly: float, lz: float) -> Vec3:
            local_y = ly + local_y_offset
            return (
                origin[0] + right[0] * lx + up[0] * local_y + forward[0] * lz,
                origin[1] + right[1] * lx + up[1] * local_y + forward[1] * lz,
                origin[2] + right[2] * lx + up[2] * local_y + forward[2] * lz,
            )

        corners: list[Vec3] = [
            local_to_world(-w / 2, -h / 2, 0.0),
            local_to_world(w / 2, -h / 2, 0.0),
            local_to_world(w / 2, h / 2, 0.0),
            local_to_world(-w / 2, h / 2, 0.0),
            local_to_world(-w / 2, -h / 2, d),
            local_to_world(w / 2, -h / 2, d),
            local_to_world(w / 2, h / 2, d),
            local_to_world(-w / 2, h / 2, d),
        ]

        edges = [
            (0, 1),
            (1, 2),
            (2, 3),
            (3, 0),
            (4, 5),
            (5, 6),
            (6, 7),
            (7, 4),
            (0, 4),
            (1, 5),
            (2, 6),
            (3, 7),
        ]

        box_pen = QPen(box_color, 2)
        if solid:
            faces = [
                (0, 1, 2, 3),
                (4, 5, 6, 7),
                (0, 1, 5, 4),
                (1, 2, 6, 5),
                (2, 3, 7, 6),
                (3, 0, 4, 7),
            ]
            face_polygons: list[tuple[float, QPolygonF]] = []
            for face in faces:
                world_face = [corners[i] for i in face]
                projected_face: list[QPointF] = []
                for point in world_face:
                    projected_point = self._project_world_point(point, context)
                    if projected_point is None:
                        projected_face = []
                        break
                    projected_face.append(projected_point)
                if len(projected_face) != 4:
                    continue
                avg_depth = sum(self._world_to_camera(p, context)[2] for p in world_face) / 4.0
                face_polygons.append((avg_depth, QPolygonF(projected_face)))
            face_polygons.sort(key=lambda item: item[0], reverse=True)

            painter.save()
            fill_color = QColor(box_color)
            fill_color.setAlpha(95)
            painter.setBrush(fill_color)
            painter.setPen(QPen(box_color, 1))
            for _, polygon in face_polygons:
                painter.drawPolygon(polygon)
            painter.restore()
        else:
            painter.setPen(box_pen)
            for i0, i1 in edges:
                projected_segment = self._project_segment_clipped(
                    corners[i0], corners[i1], context
                )
                if projected_segment is None:
                    continue
                pa, pb = projected_segment
                painter.drawLine(pa, pb)

        label_anchor = self._project_world_point(corners[6], context)
        if label_anchor is None:
            label_anchor = self._project_world_point(origin, context)
        if label_anchor is not None:
            painter.save()
            font = painter.font()
            font.setPointSize(9)
            painter.setFont(font)
            painter.setPen(QColor(0, 0, 0, 220))
            painter.drawText(label_anchor + QPointF(7.0, -5.0), label)
            painter.setPen(box_color)
            painter.drawText(label_anchor + QPointF(6.0, -6.0), label)
            painter.restore()

    def _draw_projector_holder(
        self,
        painter: QPainter,
        context: CameraContext,
        origin: Vec3,
        look_target: Vec3,
    ) -> None:
        holder_width = PROJECTOR_HOLDER_OUTER_SIZE_CM
        holder_depth = PROJECTOR_HOLDER_OUTER_SIZE_CM
        holder_height = PROJECTOR_HOLDER_OUTER_HEIGHT_CM
        inner_size = PROJECTOR_HOLDER_INNER_SIZE_CM
        lip_drop = PROJECTOR_HOLDER_INNER_DROP_CM

        forward = vec_normalize(vec_subtract(look_target, origin))
        if forward is None:
            return
        holder_min_z = (self.projector_depth * 0.5) - (holder_depth * 0.5)
        holder_origin: Vec3 = (
            origin[0] + forward[0] * holder_min_z,
            origin[1] + forward[1] * holder_min_z,
            origin[2] + forward[2] * holder_min_z,
        )

        holder_color = QColor(125, 132, 142)
        self._draw_oriented_box(
            painter,
            context,
            holder_origin,
            look_target,
            holder_color,
            "Projector Holder",
            solid=True,
            ground_to_world=True,
            ground_world_z=0.0,
            width=holder_width,
            height=holder_height,
            depth=holder_depth,
        )

        world_up: Vec3 = (0.0, 0.0, 1.0)
        if abs(vec_dot(forward, world_up)) > 0.98:
            world_up = (0.0, 1.0, 0.0)
        right = vec_normalize(vec_cross(world_up, forward))
        if right is None:
            return
        up = vec_cross(forward, right)
        local_y_offset = self._ground_alignment_local_y_offset(
            holder_origin,
            up,
            -holder_height / 2.0,
            target_world_z=0.0,
        )

        def local_to_world(lx: float, ly: float, lz: float) -> Vec3:
            local_y = ly + local_y_offset
            return (
                holder_origin[0] + right[0] * lx + up[0] * local_y + forward[0] * lz,
                holder_origin[1] + right[1] * lx + up[1] * local_y + forward[1] * lz,
                holder_origin[2] + right[2] * lx + up[2] * local_y + forward[2] * lz,
            )

        outer_top_y = holder_height / 2.0
        inner_bottom_y = outer_top_y - lip_drop
        inner_w = inner_size
        inner_d = inner_size
        inner_z0 = (holder_depth - inner_d) * 0.5
        inner_z1 = inner_z0 + inner_d
        outer = [
            local_to_world(-holder_width / 2.0, outer_top_y, 0.0),
            local_to_world(holder_width / 2.0, outer_top_y, 0.0),
            local_to_world(holder_width / 2.0, outer_top_y, holder_depth),
            local_to_world(-holder_width / 2.0, outer_top_y, holder_depth),
        ]
        inner_top = [
            local_to_world(-inner_w / 2.0, outer_top_y, inner_z0),
            local_to_world(inner_w / 2.0, outer_top_y, inner_z0),
            local_to_world(inner_w / 2.0, outer_top_y, inner_z1),
            local_to_world(-inner_w / 2.0, outer_top_y, inner_z1),
        ]
        inner_bottom = [
            local_to_world(-inner_w / 2.0, inner_bottom_y, inner_z0),
            local_to_world(inner_w / 2.0, inner_bottom_y, inner_z0),
            local_to_world(inner_w / 2.0, inner_bottom_y, inner_z1),
            local_to_world(-inner_w / 2.0, inner_bottom_y, inner_z1),
        ]

        painter.save()
        painter.setPen(QPen(QColor(178, 186, 198), 1.3))
        for i in range(4):
            outer_seg = self._project_segment_clipped(outer[i], outer[(i + 1) % 4], context)
            if outer_seg is not None:
                pa, pb = outer_seg
                painter.drawLine(pa, pb)
            inner_top_seg = self._project_segment_clipped(
                inner_top[i], inner_top[(i + 1) % 4], context
            )
            if inner_top_seg is not None:
                pa, pb = inner_top_seg
                painter.drawLine(pa, pb)
            inner_bottom_seg = self._project_segment_clipped(
                inner_bottom[i], inner_bottom[(i + 1) % 4], context
            )
            if inner_bottom_seg is not None:
                pa, pb = inner_bottom_seg
                painter.drawLine(pa, pb)
            inner_wall_seg = self._project_segment_clipped(
                inner_top[i], inner_bottom[i], context
            )
            if inner_wall_seg is not None:
                pa, pb = inner_wall_seg
                painter.drawLine(pa, pb)
            top_rim_seg = self._project_segment_clipped(
                outer[i], inner_top[i], context
            )
            if top_rim_seg is not None:
                pa, pb = top_rim_seg
                painter.drawLine(pa, pb)
        painter.restore()

    def _draw_surface_camera_mount(
        self,
        painter: QPainter,
        context: CameraContext,
        origin: Vec3,
        look_target: Vec3,
        mount_color: QColor,
        label: str,
    ) -> Vec3 | None:
        forward = vec_normalize(vec_subtract(look_target, origin))
        if forward is None:
            return None
        world_up: Vec3 = (0.0, 0.0, 1.0)
        if abs(vec_dot(forward, world_up)) > 0.98:
            world_up = (0.0, 1.0, 0.0)
        right = vec_normalize(vec_cross(world_up, forward))
        if right is None:
            return None
        up = vec_cross(forward, right)
        ground_align_local_y = 0.0
        if abs(up[2]) > 1e-6:
            ground_align_local_y = -origin[2] / up[2]

        def local_to_world(lx: float, ly: float, lz: float) -> Vec3:
            local_y = ly + ground_align_local_y
            return (
                origin[0] + right[0] * lx + up[0] * local_y + forward[0] * lz,
                origin[1] + right[1] * lx + up[1] * local_y + forward[1] * lz,
                origin[2] + right[2] * lx + up[2] * local_y + forward[2] * lz,
            )

        def draw_prism(
            local_corners: list[tuple[float, float, float]],
            color: QColor,
            fill_alpha: int,
        ) -> None:
            world_corners = [local_to_world(*corner) for corner in local_corners]
            faces = [
                (0, 1, 2, 3),
                (4, 5, 6, 7),
                (0, 1, 5, 4),
                (1, 2, 6, 5),
                (2, 3, 7, 6),
                (3, 0, 4, 7),
            ]
            edges = [
                (0, 1),
                (1, 2),
                (2, 3),
                (3, 0),
                (4, 5),
                (5, 6),
                (6, 7),
                (7, 4),
                (0, 4),
                (1, 5),
                (2, 6),
                (3, 7),
            ]
            face_polygons: list[tuple[float, QPolygonF]] = []
            for face in faces:
                world_face = [world_corners[i] for i in face]
                projected_face: list[QPointF] = []
                for point in world_face:
                    projected_point = self._project_world_point(point, context)
                    if projected_point is None:
                        projected_face = []
                        break
                    projected_face.append(projected_point)
                if len(projected_face) != 4:
                    continue
                avg_depth = sum(self._world_to_camera(p, context)[2] for p in world_face) / 4.0
                face_polygons.append((avg_depth, QPolygonF(projected_face)))
            face_polygons.sort(key=lambda item: item[0], reverse=True)

            painter.save()
            fill = QColor(color)
            fill.setAlpha(fill_alpha)
            painter.setBrush(fill)
            painter.setPen(QPen(color, 1))
            for _, polygon in face_polygons:
                painter.drawPolygon(polygon)
            painter.restore()

            painter.save()
            painter.setPen(QPen(color, 1.5))
            for i0, i1 in edges:
                projected_segment = self._project_segment_clipped(
                    world_corners[i0], world_corners[i1], context
                )
                if projected_segment is None:
                    continue
                pa, pb = projected_segment
                painter.drawLine(pa, pb)
            painter.restore()
        outer_w = SURFACE_CLAMP_OUTER_CIRCLE_DIAMETER_CM
        outer_arch_radius = outer_w * 0.5
        total_h = SURFACE_CLAMP_TOTAL_HEIGHT_CM
        bottom_y = 0.0
        arch_base_y = bottom_y + total_h - outer_arch_radius
        bottom_rect_top = bottom_y + SURFACE_CLAMP_BOTTOM_RECT_HEIGHT_CM
        front_z = SURFACE_CLAMP_THICKNESS_CM * 0.5
        back_z = -SURFACE_CLAMP_THICKNESS_CM * 0.5

        arc_segments = 24
        outer_profile: list[tuple[float, float]] = [
            (-outer_w * 0.5, bottom_y),
            (outer_w * 0.5, bottom_y),
            (outer_w * 0.5, arch_base_y),
        ]
        for i in range(arc_segments + 1):
            theta = math.pi * (i / arc_segments)
            outer_profile.append(
                (
                    math.cos(theta) * outer_arch_radius,
                    arch_base_y + math.sin(theta) * outer_arch_radius,
                )
            )
        outer_profile.append((-outer_w * 0.5, arch_base_y))

        hole_radius = SURFACE_CLAMP_INNER_CIRCLE_DIAMETER_CM * 0.5
        hole_center_y = SURFACE_CLAMP_CIRCLE_CENTER_HEIGHT_CM
        aperture_center_world = local_to_world(0.0, hole_center_y, (front_z + back_z) * 0.5)
        hole_segments = 28
        hole_profile: list[tuple[float, float]] = []
        for i in range(hole_segments):
            theta = (2.0 * math.pi * i) / hole_segments
            hole_profile.append(
                (math.cos(theta) * hole_radius, hole_center_y + math.sin(theta) * hole_radius)
            )

        def project_loop(
            profile: list[tuple[float, float]],
            z: float,
        ) -> tuple[list[Vec3], list[QPointF]] | None:
            world_points = [local_to_world(px, py, z) for px, py in profile]
            projected_points: list[QPointF] = []
            for point in world_points:
                screen_point = self._project_world_point(point, context)
                if screen_point is None:
                    return None
                projected_points.append(screen_point)
            return (world_points, projected_points)

        outer_front = project_loop(outer_profile, front_z)
        outer_back = project_loop(outer_profile, back_z)
        hole_front = project_loop(hole_profile, front_z)
        hole_back = project_loop(hole_profile, back_z)
        if (
            outer_front is None
            or outer_back is None
            or hole_front is None
            or hole_back is None
        ):
            return None

        outer_front_world, outer_front_2d = outer_front
        outer_back_world, outer_back_2d = outer_back
        hole_front_world, hole_front_2d = hole_front
        hole_back_world, hole_back_2d = hole_back

        def draw_window_face(
            outer: list[QPointF],
            hole: list[QPointF],
            color: QColor,
            alpha: int,
        ) -> None:
            path = QPainterPath()
            path.setFillRule(Qt.FillRule.OddEvenFill)
            path.addPolygon(QPolygonF(outer))
            path.addPolygon(QPolygonF(list(reversed(hole))))
            painter.save()
            fill = QColor(color)
            fill.setAlpha(alpha)
            painter.fillPath(path, fill)
            painter.setPen(QPen(color, 1.3))
            painter.drawPolygon(QPolygonF(outer))
            painter.drawPolygon(QPolygonF(hole))
            painter.restore()

        back_color = QColor(75, 106, 130)
        draw_window_face(outer_back_2d, hole_back_2d, back_color, 110)
        draw_window_face(outer_front_2d, hole_front_2d, mount_color, 145)

        # Bottom rectangular section boundary (25.10mm from ground).
        seam_front = self._project_segment_clipped(
            local_to_world(-outer_w * 0.5, bottom_rect_top, front_z),
            local_to_world(outer_w * 0.5, bottom_rect_top, front_z),
            context,
        )
        seam_back = self._project_segment_clipped(
            local_to_world(-outer_w * 0.5, bottom_rect_top, back_z),
            local_to_world(outer_w * 0.5, bottom_rect_top, back_z),
            context,
        )
        painter.save()
        painter.setPen(QPen(QColor(125, 165, 195), 1.2))
        if seam_back is not None:
            pa, pb = seam_back
            painter.drawLine(pa, pb)
        if seam_front is not None:
            pa, pb = seam_front
            painter.drawLine(pa, pb)
        painter.restore()

        painter.save()
        painter.setPen(QPen(QColor(110, 150, 180), 1))
        for i in range(len(outer_front_world)):
            segment = self._project_segment_clipped(
                outer_front_world[i],
                outer_back_world[i],
                context,
            )
            if segment is None:
                continue
            pa, pb = segment
            painter.drawLine(pa, pb)

        for i in range(0, len(hole_front_world), 2):
            segment = self._project_segment_clipped(
                hole_front_world[i],
                hole_back_world[i],
                context,
            )
            if segment is None:
                continue
            pa, pb = segment
            painter.drawLine(pa, pb)
        painter.restore()

        label_point_world = local_to_world(0.0, arch_base_y + outer_arch_radius, front_z)

        label_anchor = self._project_world_point(label_point_world, context)
        if label_anchor is None:
            label_anchor = self._project_world_point(origin, context)
        if label_anchor is not None:
            painter.save()
            font = painter.font()
            font.setPointSize(9)
            painter.setFont(font)
            painter.setPen(QColor(0, 0, 0, 220))
            painter.drawText(label_anchor + QPointF(7.0, -5.0), label)
            painter.setPen(mount_color)
            painter.drawText(label_anchor + QPointF(6.0, -6.0), label)
            painter.restore()
        return aperture_center_world

    def _draw_device_boxes(
        self, painter: QPainter, viewport_width: int, viewport_height: int
    ) -> None:
        self._clamp_projection_hit_world = None
        self._clamp_ray_origin_world = None
        context = self._camera_projection_context(viewport_width, viewport_height)
        if context is None:
            return

        w = self.projector_width
        h = self.projector_height
        d = self.projector_depth
        if w <= 0 or h <= 0 or d <= 0:
            return

        projector_origin: Vec3 = (
            self._projector_pos[0],
            self._projector_pos[1],
            self._projector_pos[2],
        )
        surface_camera_origin: Vec3 = (
            self._surface_camera_pos[0],
            self._surface_camera_pos[1],
            self._surface_camera_pos[2],
        )
        projector_look_target = self._projector_horizontal_target(projector_origin)
        surface_camera_look_target = self._projector_horizontal_target(surface_camera_origin)
        self._draw_projector_holder(
            painter,
            context,
            projector_origin,
            projector_look_target,
        )
        self._draw_oriented_box(
            painter,
            context,
            projector_origin,
            projector_look_target,
            QColor(255, 146, 56),
            "Projector",
            solid=True,
            ground_to_world=True,
            ground_world_z=PROJECTOR_HOLDER_HEIGHT_CM,
        )
        aperture_center = self._draw_surface_camera_mount(
            painter,
            context,
            surface_camera_origin,
            surface_camera_look_target,
            QColor(56, 180, 255),
            "56027 Clamp",
        )
        if aperture_center is None:
            return
        self._clamp_ray_origin_world = aperture_center
        projection_surface = self._primary_projection_surface()
        if projection_surface is None:
            return
        surface_center, surface_width, surface_height = projection_surface
        surface_world = self._surface_world_corners(surface_center, surface_width, surface_height)
        edge_u = vec_subtract(surface_world[1], surface_world[0])
        edge_v = vec_subtract(surface_world[3], surface_world[0])
        plane_normal = vec_normalize(vec_cross(edge_u, edge_v))
        clamp_ray_target = self._projector_horizontal_target(aperture_center)
        camera_axis_target = vec_normalize(vec_subtract(clamp_ray_target, aperture_center))
        ray_direction = camera_axis_target
        contour_hit: Vec3 | None = None
        if plane_normal is not None and ray_direction is not None:
            contour_hit = self._intersect_ray_with_plane(
                aperture_center,
                ray_direction,
                surface_world[0],
                plane_normal,
            )
        if contour_hit is None:
            contour_hit = surface_center
        self._clamp_projection_hit_world = contour_hit
        contour_segment = self._project_segment_clipped(aperture_center, contour_hit, context)
        if contour_segment is not None:
            painter.save()
            painter.setPen(QPen(QColor(92, 222, 255, 210), 1.5))
            pa, pb = contour_segment
            painter.drawLine(pa, pb)
            painter.restore()

