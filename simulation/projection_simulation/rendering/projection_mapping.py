from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QTransform

from ..core.constants import (
    PROJECTOR_RAYCAST_COLUMNS,
    PROJECTOR_RAYCAST_EDGE_SUBDIVISIONS,
    PROJECTOR_RAYCAST_ROWS,
)
from ..core.types import CameraContext, Vec3
from ..core.math3d import vec_cross, vec_dot, vec_normalize, vec_subtract
from .projection_raycasting import ProjectionRaycastingMixin

SceneSurface = tuple[str, list[Vec3], QColor]
TelecentricScanContext = tuple[Vec3, Vec3, Vec3, Vec3, float, float]
FringeRectContext = tuple[Vec3, Vec3, Vec3, Vec3, float, float, float, float]


class ProjectionMappingMixin(ProjectionRaycastingMixin):
    def _draw_projected_source_quad(
        self,
        painter: QPainter,
        pixmap: QPixmap,
        source_quad: QPolygonF,
        destination_quad: QPolygonF,
        *,
        clip_quad: QPolygonF | None = None,
    ) -> None:
        with self._profile_section("_draw_projected_source_quad"):
            transform = QTransform.quadToQuad(source_quad, destination_quad)
            if not isinstance(transform, QTransform):
                return

            painter.save()
            clip_path = QPainterPath()
            clip_path.addPolygon(clip_quad if clip_quad is not None else destination_quad)
            painter.setClipPath(clip_path)
            painter.setTransform(transform, True)
            painter.drawPixmap(0, 0, pixmap)
            painter.restore()

    def _draw_solid_quad(
        self,
        painter: QPainter,
        destination_quad: QPolygonF,
        color: QColor,
    ) -> None:
        painter.save()
        painter.setPen(QPen(QColor(120, 130, 150), 1))
        painter.setBrush(color)
        painter.drawPolygon(destination_quad)
        painter.restore()

    def _primary_surface_fringe_context(
        self,
        image_width: int,
        image_height: int,
        scan_context: TelecentricScanContext | None,
    ) -> FringeRectContext | None:
        primary_surface = self._primary_projection_surface()
        if primary_surface is None or scan_context is None:
            return None
        surface_center, surface_width, surface_height = primary_surface
        surface_corners = self._surface_world_corners(
            surface_center,
            surface_width,
            surface_height,
        )
        if len(surface_corners) != 4:
            return None
        origin = surface_corners[3]
        right = vec_normalize(vec_subtract(surface_corners[2], surface_corners[3]))
        up = vec_normalize(vec_subtract(surface_corners[0], surface_corners[3]))
        if right is None or up is None:
            return None
        normal = vec_normalize(vec_cross(right, up))
        if normal is None:
            return None

        corner_samples = [
            (0.0, 0.0),
            (float(image_width), 0.0),
            (float(image_width), float(image_height)),
            (0.0, float(image_height)),
        ]
        u_values: list[float] = []
        v_values: list[float] = []
        forward = scan_context[3]
        for sx, sy in corner_samples:
            ray_origin = self._telecentric_ray_origin(
                sx,
                sy,
                image_width,
                image_height,
                scan_context,
            )
            if ray_origin is None:
                return None
            hit = self._intersect_ray_with_plane(
                ray_origin,
                forward,
                origin,
                normal,
            )
            if hit is None:
                return None
            rel = vec_subtract(hit, origin)
            u_values.append(vec_dot(rel, right))
            v_values.append(vec_dot(rel, up))

        return (
            origin,
            normal,
            right,
            up,
            min(u_values),
            max(u_values),
            min(v_values),
            max(v_values),
        )

    def _projector_hit_on_fringe_plane(
        self,
        x_pixel: float,
        y_pixel: float,
        image_width: int,
        image_height: int,
        projector_context: tuple[Vec3, Vec3, Vec3, Vec3, float, float],
        fringe_context: FringeRectContext | None,
    ) -> Vec3 | None:
        with self._profile_section("_projector_hit_on_fringe_plane"):
            if fringe_context is None:
                return None
            ray_direction = self._projector_ray_direction(
                x_pixel,
                y_pixel,
                image_width,
                image_height,
                projector_context,
            )
            if ray_direction is None:
                return None
            plane_origin, plane_normal, _, _, _, _, _, _ = fringe_context
            return self._intersect_ray_with_plane(
                projector_context[0],
                ray_direction,
                plane_origin,
                plane_normal,
            )

    def _draw_projected_scene(
        self,
        painter: QPainter,
        pixmap: QPixmap,
        viewport_width: int,
        viewport_height: int,
        *,
        view_context: CameraContext | None = None,
        columns: int = PROJECTOR_RAYCAST_COLUMNS,
        rows: int = PROJECTOR_RAYCAST_ROWS,
        edge_subdivisions: int = PROJECTOR_RAYCAST_EDGE_SUBDIVISIONS,
        projector_context: tuple[Vec3, Vec3, Vec3, Vec3, float, float] | None = None,
        scene_surfaces: list[SceneSurface] | None = None,
    ) -> bool:
        with self._profile_section("_draw_projected_scene"):
            if pixmap.width() <= 0 or pixmap.height() <= 0:
                return False
            if view_context is None:
                view_context = self._camera_projection_context(viewport_width, viewport_height)
            if view_context is None:
                return False
            if projector_context is None:
                projector_context = self._projector_projection_context(pixmap.width(), pixmap.height())
            if projector_context is None:
                return False

            surfaces = scene_surfaces if scene_surfaces is not None else self._scene_surfaces()
            if not surfaces:
                return False

            surface_cells: list[list[tuple[QPolygonF, QPolygonF]]] = [
                [] for _ in surfaces
            ]
            columns = max(2, columns)
            rows = max(2, rows)
            edge_subdivisions = max(0, edge_subdivisions)
            for row in range(rows):
                y0 = pixmap.height() * row / rows
                y1 = pixmap.height() * (row + 1) / rows
                for column in range(columns):
                    x0 = pixmap.width() * column / columns
                    x1 = pixmap.width() * (column + 1) / columns
                    self._add_projected_cell(
                        surface_cells,
                        surfaces,
                        pixmap,
                        view_context,
                        projector_context,
                        None,
                        None,
                        x0,
                        y0,
                        x1,
                        y1,
                        edge_subdivisions,
                    )

            surface_order: list[tuple[float, int, QPolygonF]] = []
            for index, (_, corners, _) in enumerate(surfaces):
                projected_surface: list[QPointF] = []
                for corner in corners:
                    projected = self._project_world_point(corner, view_context)
                    if projected is None:
                        projected_surface = []
                        break
                    projected_surface.append(projected)
                if len(projected_surface) != len(corners):
                    continue
                avg_depth = sum(
                    self._world_to_camera(corner, view_context)[2] for corner in corners
                ) / len(corners)
                surface_order.append((avg_depth, index, QPolygonF(projected_surface)))

            if not surface_order:
                return False
            surface_order.sort(key=lambda item: item[0], reverse=True)
            for _, surface_index, projected_surface in surface_order:
                _, _, color = surfaces[surface_index]
                self._draw_solid_quad(painter, projected_surface, color)
                for source_quad, destination_quad in surface_cells[surface_index]:
                    self._draw_projected_source_quad(
                        painter,
                        pixmap,
                        source_quad,
                        destination_quad,
                        clip_quad=projected_surface,
                    )
            return True

    def _add_projected_cell(
        self,
        surface_cells: list[list[tuple[QPolygonF, QPolygonF]]],
        surfaces: list[SceneSurface],
        pixmap: QPixmap,
        view_context: CameraContext,
        projector_context: tuple[Vec3, Vec3, Vec3, Vec3, float, float],
        scan_mask_context: TelecentricScanContext | None,
        fringe_rect_context: FringeRectContext | None,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        remaining_subdivisions: int,
    ) -> None:
        with self._profile_section("_add_projected_cell"):
            sample_points = [
                ((x0 + x1) * 0.5, (y0 + y1) * 0.5),
                (x0, y0),
                ((x0 + x1) * 0.5, y0),
                (x1, y0),
                (x1, (y0 + y1) * 0.5),
                (x1, y1),
                ((x0 + x1) * 0.5, y1),
                (x0, y1),
                (x0, (y0 + y1) * 0.5),
            ]
            sample_hits: list[tuple[int, bool]] = []
            for sx, sy in sample_points:
                hit = self._first_projector_hit(
                    sx,
                    sy,
                    pixmap.width(),
                    pixmap.height(),
                    projector_context,
                    surfaces,
                )
                if hit is not None:
                    mask_point = hit[1]
                    inside_mask = self._world_point_inside_projection_context(
                        mask_point,
                        scan_mask_context,
                    )
                    if fringe_rect_context is not None:
                        plane_hit = self._projector_hit_on_fringe_plane(
                            sx,
                            sy,
                            pixmap.width(),
                            pixmap.height(),
                            projector_context,
                            fringe_rect_context,
                        )
                        if plane_hit is None:
                            continue
                        mask_point = plane_hit
                        inside_mask = self._world_point_inside_fringe_rect(
                            mask_point,
                            fringe_rect_context,
                        )
                    sample_hits.append(
                        (
                            hit[0],
                            inside_mask,
                        )
                    )

            if not sample_hits:
                return
            center_surface_index, center_inside_mask = sample_hits[0]
            if (
                remaining_subdivisions > 0
                and any(
                    surface_index != center_surface_index or inside_mask != center_inside_mask
                    for surface_index, inside_mask in sample_hits[1:]
                )
            ):
                xm = (x0 + x1) * 0.5
                ym = (y0 + y1) * 0.5
                next_depth = remaining_subdivisions - 1
                self._add_projected_cell(
                    surface_cells,
                    surfaces,
                    pixmap,
                    view_context,
                    projector_context,
                    scan_mask_context,
                    fringe_rect_context,
                    x0,
                    y0,
                    xm,
                    ym,
                    next_depth,
                )
                self._add_projected_cell(
                    surface_cells,
                    surfaces,
                    pixmap,
                    view_context,
                    projector_context,
                    scan_mask_context,
                    fringe_rect_context,
                    xm,
                    y0,
                    x1,
                    ym,
                    next_depth,
                )
                self._add_projected_cell(
                    surface_cells,
                    surfaces,
                    pixmap,
                    view_context,
                    projector_context,
                    scan_mask_context,
                    fringe_rect_context,
                    xm,
                    ym,
                    x1,
                    y1,
                    next_depth,
                )
                self._add_projected_cell(
                    surface_cells,
                    surfaces,
                    pixmap,
                    view_context,
                    projector_context,
                    scan_mask_context,
                    fringe_rect_context,
                    x0,
                    ym,
                    xm,
                    y1,
                    next_depth,
                )
                return
            if not center_inside_mask:
                return

            source_points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            surface_corners = surfaces[center_surface_index][1]
            edge_u = vec_subtract(surface_corners[1], surface_corners[0])
            edge_v = vec_subtract(surface_corners[-1], surface_corners[0])
            surface_normal = vec_normalize(vec_cross(edge_u, edge_v))
            if surface_normal is None:
                return

            hit_points: list[Vec3] = []
            for sx, sy in source_points:
                ray_direction = self._projector_ray_direction(
                    sx,
                    sy,
                    pixmap.width(),
                    pixmap.height(),
                    projector_context,
                )
                if ray_direction is None:
                    return
                hit = self._intersect_ray_with_plane(
                    projector_context[0],
                    ray_direction,
                    surface_corners[0],
                    surface_normal,
                )
                if hit is None:
                    return
                hit_points.append(hit)

            destination_points = [
                self._project_world_point(hit, view_context)
                for hit in hit_points
            ]
            if any(point is None for point in destination_points):
                return

            if fringe_rect_context is not None:
                source_quad_points: list[QPointF] = []
                for sx, sy in source_points:
                    plane_hit = self._projector_hit_on_fringe_plane(
                        sx,
                        sy,
                        pixmap.width(),
                        pixmap.height(),
                        projector_context,
                        fringe_rect_context,
                    )
                    if plane_hit is None:
                        return
                    source_point = self._fringe_source_point_for_world(
                        plane_hit,
                        fringe_rect_context,
                        pixmap.width(),
                        pixmap.height(),
                    )
                    if source_point is None:
                        return
                    source_quad_points.append(source_point)
                source_quad = QPolygonF(source_quad_points)
            else:
                source_quad = QPolygonF([QPointF(sx, sy) for sx, sy in source_points])
            destination_quad = QPolygonF([point for point in destination_points if point is not None])
            surface_cells[center_surface_index].append((source_quad, destination_quad))

    def _world_point_inside_projection_context(
        self,
        point: Vec3,
        context: TelecentricScanContext | None,
    ) -> bool:
        if context is None:
            return True
        origin, right, up, forward, half_w, half_h = context
        rel = vec_subtract(point, origin)
        depth = vec_dot(rel, forward)
        if depth <= 1e-5:
            return False
        if half_w <= 1e-9 or half_h <= 1e-9:
            return False
        lateral_x = vec_dot(rel, right)
        lateral_y = vec_dot(rel, up)
        return abs(lateral_x) <= half_w + 1e-5 and abs(lateral_y) <= half_h + 1e-5

    def _world_point_inside_fringe_rect(
        self,
        point: Vec3,
        context: FringeRectContext | None,
    ) -> bool:
        if context is None:
            return True
        origin, _, right, up, u_min, u_max, v_min, v_max = context
        rel = vec_subtract(point, origin)
        u = vec_dot(rel, right)
        v = vec_dot(rel, up)
        return (
            u_min - 1e-5 <= u <= u_max + 1e-5
            and v_min - 1e-5 <= v <= v_max + 1e-5
        )

    def _fringe_source_point_for_world(
        self,
        point: Vec3,
        context: FringeRectContext,
        image_width: int,
        image_height: int,
    ) -> QPointF | None:
        origin, _, right, up, u_min, u_max, v_min, v_max = context
        span_u = u_max - u_min
        span_v = v_max - v_min
        if span_u <= 1e-6 or span_v <= 1e-6:
            return None
        rel = vec_subtract(point, origin)
        u = vec_dot(rel, right)
        v = vec_dot(rel, up)
        if not self._world_point_inside_fringe_rect(point, context):
            return None
        nx = (u - u_min) / span_u
        ny = 1.0 - ((v - v_min) / span_v)
        x = nx * float(image_width)
        y = ny * float(image_height)
        return QPointF(x, y)

    def _fringe_source_point_for_projector_ray(
        self,
        point: Vec3,
        projector_context: tuple[Vec3, Vec3, Vec3, Vec3, float, float],
        fringe_context: FringeRectContext,
        image_width: int,
        image_height: int,
    ) -> QPointF | None:
        projector_origin = projector_context[0]
        fringe_origin, fringe_normal, _, _, _, _, _, _ = fringe_context
        ray = vec_subtract(point, projector_origin)
        denominator = vec_dot(ray, fringe_normal)
        if abs(denominator) <= 1e-8:
            return None
        t = vec_dot(vec_subtract(fringe_origin, projector_origin), fringe_normal) / denominator
        if t <= 1e-5:
            return None
        plane_point = (
            projector_origin[0] + ray[0] * t,
            projector_origin[1] + ray[1] * t,
            projector_origin[2] + ray[2] * t,
        )
        return self._fringe_source_point_for_world(
            plane_point,
            fringe_context,
            image_width,
            image_height,
        )

    def _projector_source_point_for_world(
        self,
        point: Vec3,
        projector_context: tuple[Vec3, Vec3, Vec3, Vec3, float, float],
        image_width: int,
        image_height: int,
    ) -> QPointF | None:
        origin, right, up, forward, tan_half_fov, aspect = projector_context
        rel = vec_subtract(point, origin)
        depth = vec_dot(rel, forward)
        if depth <= 1e-5:
            return None
        if abs(tan_half_fov) <= 1e-9 or aspect <= 1e-9:
            return None
        nx = vec_dot(rel, right) / (depth * aspect * tan_half_fov)
        ny = vec_dot(rel, up) / (depth * tan_half_fov)
        if nx < -1.0 or nx > 1.0 or ny < -1.0 or ny > 1.0:
            return None
        return QPointF(
            (nx + 1.0) * 0.5 * float(image_width),
            (1.0 - ny) * 0.5 * float(image_height),
        )

