from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF

from ..core.constants import (
    FIELD_OBJECT_PLANE_GAP_M,
    PROJECTOR_IMAGE_ASPECT,
    PROJECTOR_LENS_FACE_EPS,
    PROJECTOR_LENS_WINDOW_HEIGHT_CM,
    PROJECTOR_LENS_WINDOW_WIDTH_CM,
)
from ..core.math3d import vec_cross, vec_dot, vec_normalize, vec_subtract
from ..core.types import Vec3
from .render_scene import CameraView, FringeRect, ProjectionScene, ProjectorView, RenderLine, RenderSurface, TelecentricScan, ViewportRect
from ..scanning.scan_pipeline import nuanced_field_object_faces

SceneSurface = tuple[str, list[Vec3], QColor]
TelecentricScanContext = tuple[Vec3, Vec3, Vec3, Vec3, float, float]
FringeRectContext = tuple[Vec3, Vec3, Vec3, Vec3, float, float, float, float]


class SceneAssemblyMixin:
    def _build_projection_scene(
        self,
        viewport_width: int,
        viewport_height: int,
        *,
        include_minimap: bool,
        include_grid: bool = True,
    ) -> ProjectionScene | None:
        if self.mode != "plane3d":
            return None
        if self._processed.width() <= 0 or self._processed.height() <= 0:
            return None
        main_context = self._camera_projection_context(viewport_width, viewport_height)
        projector_context = self._projector_projection_context(
            self._processed.width(),
            self._processed.height(),
        )
        if main_context is None or projector_context is None:
            return None

        surfaces = tuple(
            RenderSurface(name, tuple(corners[:4]), color)
            for name, corners, color in self._scene_surfaces()
            if len(corners) >= 4
        )
        if not surfaces:
            return None

        scan_context = self._surface_camera_telecentric_scan_context(
            self._processed.width(),
            self._processed.height(),
        )
        fringe_context = (
            self._primary_surface_fringe_context(
                self._processed.width(),
                self._processed.height(),
                scan_context,
            )
            if self.projection_source == "fringe"
            else None
        )

        viewport_scan_context = (
            self._surface_camera_telecentric_scan_context(
                viewport_width,
                viewport_height,
            )
            if getattr(self, "_viewport_scan_capture", False)
            else None
        )
        main_view = (
            self._telecentric_camera_view_from_context(viewport_scan_context)
            if viewport_scan_context is not None
            else self._camera_view_from_context(main_context, self.fov_deg)
        )

        minimap_view: CameraView | None = None
        minimap_viewport: ViewportRect | None = None
        if include_minimap and viewport_scan_context is None:
            minimap_viewport = self._surface_camera_minimap_viewport(
                viewport_width,
                viewport_height,
            )
            minimap_context = self._surface_camera_telecentric_scan_context(
                minimap_viewport.width,
                minimap_viewport.height,
            )
            if minimap_context is not None:
                minimap_view = self._telecentric_camera_view_from_context(minimap_context)

        return ProjectionScene(
            source_image=self._processed,
            source_is_fringe=self.projection_source == "fringe",
            surfaces=surfaces,
            lines=(
                self._ground_grid_render_lines()
                if include_grid and self.show_ground_grid
                else ()
            ),
            main_view=main_view,
            projector=self._projector_view_from_context(projector_context),
            scan=(
                self._telecentric_scan_from_context(scan_context)
                if scan_context is not None
                else None
            ),
            fringe_rect=(
                self._fringe_rect_from_context(fringe_context)
                if fringe_context is not None
                else None
            ),
            minimap_view=minimap_view,
            minimap_viewport=minimap_viewport if minimap_view is not None else None,
        )

    def _ground_grid_render_lines(self) -> tuple[RenderLine, ...]:
        steps = int(self.grid_extent / self.grid_step)
        if steps <= 0:
            return ()

        lines: list[RenderLine] = []
        minor = QColor(55, 55, 55)
        major = QColor(95, 95, 95)
        axis = QColor(150, 150, 150)
        for i in range(-steps, steps + 1):
            coord = i * self.grid_step
            color = minor
            if i == 0:
                color = axis
            elif i % self.grid_major_every == 0:
                color = major
            lines.append(
                RenderLine(
                    (coord, -self.grid_extent, 0.0),
                    (coord, self.grid_extent, 0.0),
                    color,
                )
            )
            lines.append(
                RenderLine(
                    (-self.grid_extent, coord, 0.0),
                    (self.grid_extent, coord, 0.0),
                    color,
                )
            )
        return tuple(lines)

    def _surface_camera_minimap_viewport(
        self,
        viewport_width: int,
        viewport_height: int,
    ) -> ViewportRect:
        inset_margin = 12
        inset_width = max(220, min(360, int(viewport_width * 0.30)))
        inset_height = max(140, int(inset_width * 9.0 / 16.0))
        if inset_height > viewport_height - inset_margin * 2:
            inset_height = max(120, viewport_height - inset_margin * 2)
            inset_width = max(180, int(inset_height * 16.0 / 9.0))
        return ViewportRect(
            viewport_width - inset_width - inset_margin,
            inset_margin,
            inset_width,
            inset_height,
        )

    def _draw_surface_camera_minimap_chrome(self, painter: QPainter) -> None:
        viewport = self._surface_camera_minimap_viewport(self.width(), self.height())
        painter.save()
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(190, 200, 220, 220), 1))
        painter.drawRect(viewport.x, viewport.y, viewport.width, viewport.height)
        painter.setPen(QColor(220, 230, 245, 220))
        painter.drawText(viewport.x + 8, viewport.y + 16, "Surface Camera Capture")
        painter.restore()

    def _camera_view_from_context(
        self,
        context: CameraContext,
        fov_deg: float,
    ) -> CameraView:
        camera, right, up, forward, _, _, _ = context
        return CameraView(camera, right, up, forward, fov_deg)

    def _projector_view_from_context(
        self,
        context: tuple[Vec3, Vec3, Vec3, Vec3, float, float],
    ) -> ProjectorView:
        origin, right, up, forward, tan_half_fov, aspect = context
        return ProjectorView(origin, right, up, forward, tan_half_fov, aspect)

    def _telecentric_scan_from_context(
        self,
        context: TelecentricScanContext,
    ) -> TelecentricScan:
        origin, right, up, forward, half_width, half_height = context
        return TelecentricScan(origin, right, up, forward, half_width, half_height)

    def _telecentric_camera_view_from_context(
        self,
        context: TelecentricScanContext,
    ) -> CameraView:
        origin, right, up, forward, half_width, half_height = context
        return CameraView(
            origin,
            right,
            up,
            forward,
            self._effective_projector_fov_deg(),
            half_width,
            half_height,
        )

    def _fringe_rect_from_context(
        self,
        context: FringeRectContext,
    ) -> FringeRect:
        origin, normal, right, up, u_min, u_max, v_min, v_max = context
        return FringeRect(origin, normal, right, up, u_min, u_max, v_min, v_max)

    def _draw_scaled_fit(self, painter: QPainter, pixmap: QPixmap) -> None:
        mode = Qt.KeepAspectRatioByExpanding if self.fill else Qt.KeepAspectRatio
        scaled = pixmap.size().scaled(self.size(), mode)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled.width(), scaled.height(), pixmap)

    def _draw_plane3d_projection(
        self,
        painter: QPainter,
        pixmap: QPixmap,
        *,
        projector_context: tuple[Vec3, Vec3, Vec3, Vec3, float, float] | None = None,
        scene_surfaces: list[SceneSurface] | None = None,
    ) -> bool:
        return self._draw_projected_scene(
            painter,
            pixmap,
            self.width(),
            self.height(),
            projector_context=projector_context,
            scene_surfaces=scene_surfaces,
        )

    def _draw_scene_surface_wireframes(
        self,
        painter: QPainter,
        viewport_width: int,
        viewport_height: int,
    ) -> None:
        context = self._camera_projection_context(viewport_width, viewport_height)
        if context is None:
            return
        painter.save()
        for name, corners, _ in self._scene_surfaces():
            if len(corners) < 4:
                continue
            if name == "Projection Plane":
                painter.setPen(QPen(QColor(120, 130, 150, 190), 1.0))
            else:
                painter.setPen(QPen(QColor(95, 132, 170, 220), 1.2))
            for index, start in enumerate(corners):
                end = corners[(index + 1) % len(corners)]
                segment = self._project_segment_clipped(start, end, context)
                if segment is None:
                    continue
                painter.drawLine(*segment)
        painter.restore()

    def _draw_field_object_3d(
        self,
        painter: QPainter,
        viewport_width: int,
        viewport_height: int,
        *,
        context: CameraContext | None = None,
    ) -> bool:
        if self.field_width_m <= 0 or self.field_height_m <= 0:
            return False
        if context is None:
            context = self._camera_projection_context(viewport_width, viewport_height)
        if context is None:
            return False

        face_polygons: list[tuple[float, QPolygonF]] = []
        for face_world in self._field_object_faces():
            projected_face: list[QPointF] = []
            for point in face_world:
                projected = self._project_world_point(point, context)
                if projected is None:
                    projected_face = []
                    break
                projected_face.append(projected)
            if len(projected_face) != 4:
                continue
            avg_depth = sum(self._world_to_camera(p, context)[2] for p in face_world) / 4.0
            face_polygons.append((avg_depth, QPolygonF(projected_face)))

        if not face_polygons:
            return False

        face_polygons.sort(key=lambda item: item[0], reverse=True)
        painter.save()
        painter.setPen(QPen(QColor(95, 132, 170), 1.2))
        painter.setBrush(QColor(70, 96, 124, 140))
        for _, polygon in face_polygons:
            painter.drawPolygon(polygon)
        painter.restore()
        return True

    def _field_object_world_corners(self) -> list[Vec3]:
        frame = self._field_object_frame()
        if frame is None:
            return []
        plane_center, right, up, normal = frame
        half_w = self.field_width_m * 0.5
        half_h = self.field_height_m * 0.5
        depth = self._field_object_depth()
        gap = FIELD_OBJECT_PLANE_GAP_M
        back_center = (
            plane_center[0] + normal[0] * gap,
            plane_center[1] + normal[1] * gap,
            plane_center[2] + normal[2] * gap,
        )
        front_center = (
            plane_center[0] + normal[0] * (gap + depth),
            plane_center[1] + normal[1] * (gap + depth),
            plane_center[2] + normal[2] * (gap + depth),
        )

        def rect(center: Vec3) -> list[Vec3]:
            return [
                (
                    center[0] - right[0] * half_w + up[0] * half_h,
                    center[1] - right[1] * half_w + up[1] * half_h,
                    center[2] - right[2] * half_w + up[2] * half_h,
                ),
                (
                    center[0] + right[0] * half_w + up[0] * half_h,
                    center[1] + right[1] * half_w + up[1] * half_h,
                    center[2] + right[2] * half_w + up[2] * half_h,
                ),
                (
                    center[0] + right[0] * half_w - up[0] * half_h,
                    center[1] + right[1] * half_w - up[1] * half_h,
                    center[2] + right[2] * half_w - up[2] * half_h,
                ),
                (
                    center[0] - right[0] * half_w - up[0] * half_h,
                    center[1] - right[1] * half_w - up[1] * half_h,
                    center[2] - right[2] * half_w - up[2] * half_h,
                ),
            ]

        return [*rect(front_center), *rect(back_center)]

    def _field_object_faces(self) -> list[list[Vec3]]:
        if self.field_object_kind == "nuanced":
            return nuanced_field_object_faces(self)
        world_corners = self._field_object_world_corners()
        if len(world_corners) != 8:
            return []
        face_indices = [
            (0, 1, 2, 3),
            (4, 5, 6, 7),
            (0, 1, 5, 4),
            (1, 2, 6, 5),
            (2, 3, 7, 6),
            (3, 0, 4, 7),
        ]
        return [[world_corners[i] for i in face] for face in face_indices]

    def _field_object_depth(self) -> float:
        return max(0.25, min(self.field_width_m, self.field_height_m) * 0.6)

    def _field_object_frame(self) -> tuple[Vec3, Vec3, Vec3, Vec3] | None:
        plane_center = self._plane_center()
        corners = self._surface_world_corners(
            plane_center,
            self.plane_width_m,
            self.plane_height_m,
        )
        right = vec_normalize(vec_subtract(corners[1], corners[0]))
        up = vec_normalize(vec_subtract(corners[0], corners[3]))
        if right is None or up is None:
            return None
        normal = vec_normalize(vec_cross(right, up))
        if normal is None:
            return None
        if vec_dot(normal, self._symmetry_normal) < 0.0:
            normal = (-normal[0], -normal[1], -normal[2])
        return (plane_center, right, up, normal)

    def _scene_surfaces(self) -> list[SceneSurface]:
        surfaces: list[SceneSurface] = []
        if self.project_projection_plane:
            surfaces.append(
                (
                    "Projection Plane",
                    self._surface_world_corners(
                        self._plane_center(),
                        self.plane_width_m,
                        self.plane_height_m,
                    ),
                    QColor(56, 64, 82),
                )
            )
        if self.project_field_object:
            for index, face in enumerate(self._field_object_faces()):
                surfaces.append((f"Field Object {index + 1}", face, QColor(70, 96, 124)))
        return surfaces

    def _surface_corners(
        self, center: Vec3, width: float, height: float
    ) -> list[Vec3]:
        half_w = width / 2.0
        half_h = height / 2.0
        if self.projector_axis == "y":
            return [
                (center[0] - half_w, center[1], center[2] + half_h),
                (center[0] + half_w, center[1], center[2] + half_h),
                (center[0] + half_w, center[1], center[2] - half_h),
                (center[0] - half_w, center[1], center[2] - half_h),
            ]
        return [
            (center[0] - half_w, center[1] + half_h, center[2]),
            (center[0] + half_w, center[1] + half_h, center[2]),
            (center[0] + half_w, center[1] - half_h, center[2]),
            (center[0] - half_w, center[1] - half_h, center[2]),
        ]

    def _surface_world_corners(
        self, center: Vec3, width: float, height: float
    ) -> list[Vec3]:
        return [
            self._rotate_plane_point(corner, center)
            for corner in self._surface_corners(center, width, height)
        ]

    def _projector_projection_context(
        self, image_width: int, image_height: int
    ) -> tuple[Vec3, Vec3, Vec3, Vec3, float, float] | None:
        if image_width <= 0 or image_height <= 0:
            return None
        axes = self._projector_axes()
        if axes is None:
            return None
        origin, right, up, forward = axes
        aspect = float(image_width) / float(image_height)
        effective_fov_deg = self._effective_projector_fov_deg()
        tan_half_fov = math.tan(math.radians(effective_fov_deg) / 2.0)
        return (origin, right, up, forward, tan_half_fov, aspect)

    def _lens_plane_corners(
        self,
        center: Vec3,
        right: Vec3,
        up: Vec3,
        width: float,
        height: float,
    ) -> list[Vec3]:
        half_w = width * 0.5
        half_h = height * 0.5
        return [
            (
                center[0] - right[0] * half_w + up[0] * half_h,
                center[1] - right[1] * half_w + up[1] * half_h,
                center[2] - right[2] * half_w + up[2] * half_h,
            ),
            (
                center[0] + right[0] * half_w + up[0] * half_h,
                center[1] + right[1] * half_w + up[1] * half_h,
                center[2] + right[2] * half_w + up[2] * half_h,
            ),
            (
                center[0] + right[0] * half_w - up[0] * half_h,
                center[1] + right[1] * half_w - up[1] * half_h,
                center[2] + right[2] * half_w - up[2] * half_h,
            ),
            (
                center[0] - right[0] * half_w - up[0] * half_h,
                center[1] - right[1] * half_w - up[1] * half_h,
                center[2] - right[2] * half_w - up[2] * half_h,
            ),
        ]

    def _projector_horizontal_target(self, origin: Vec3) -> Vec3:
        target = self._look_target()
        primary_surface = self._primary_projection_surface()
        if primary_surface is not None:
            target = primary_surface[0]
        return (target[0], target[1], origin[2])

    def _horizontal_forward_direction(self, origin: Vec3) -> Vec3:
        target = self._projector_horizontal_target(origin)
        direction = vec_normalize((target[0] - origin[0], target[1] - origin[1], 0.0))
        if direction is not None:
            return direction
        tangent = vec_normalize((self._symmetry_tangent[0], self._symmetry_tangent[1], 0.0))
        if tangent is not None:
            return tangent
        return (0.0, 1.0, 0.0)

    def _projector_chassis_axes(self) -> tuple[Vec3, Vec3, Vec3, Vec3] | None:
        chassis_origin = self._projector_pos
        forward = self._horizontal_forward_direction(chassis_origin)
        world_up: Vec3 = (0.0, 0.0, 1.0)
        if abs(vec_dot(forward, world_up)) > 0.98:
            world_up = (0.0, 1.0, 0.0)
        right = vec_normalize(vec_cross(forward, world_up))
        if right is None:
            return None
        up = vec_cross(right, forward)
        return (chassis_origin, right, up, forward)

    def _projector_lens_rectangle_world(self) -> tuple[list[Vec3], Vec3] | None:
        chassis_axes = self._projector_chassis_axes()
        if chassis_axes is None:
            return None
        chassis_origin, right, up, forward = chassis_axes

        lens_half_w = PROJECTOR_LENS_WINDOW_WIDTH_CM * 0.5
        lens_half_h = PROJECTOR_LENS_WINDOW_HEIGHT_CM * 0.5
        cx = self.projector_lens_offset_x
        cy = self.projector_lens_offset_y
        cz = self.projector_lens_offset_z + PROJECTOR_LENS_FACE_EPS

        def local_to_world(lx: float, ly: float, lz: float) -> Vec3:
            return (
                chassis_origin[0] + right[0] * lx + up[0] * ly + forward[0] * lz,
                chassis_origin[1] + right[1] * lx + up[1] * ly + forward[1] * lz,
                chassis_origin[2] + right[2] * lx + up[2] * ly + forward[2] * lz,
            )

        center = local_to_world(cx, cy, cz)
        corners: list[Vec3] = [
            local_to_world(cx - lens_half_w, cy + lens_half_h, cz),
            local_to_world(cx + lens_half_w, cy + lens_half_h, cz),
            local_to_world(cx + lens_half_w, cy - lens_half_h, cz),
            local_to_world(cx - lens_half_w, cy - lens_half_h, cz),
        ]
        return (corners, center)

    def _projector_axes(self) -> tuple[Vec3, Vec3, Vec3, Vec3] | None:
        lens_data = self._projector_lens_rectangle_world()
        if lens_data is None:
            return None
        _, lens_origin = lens_data
        lens_forward = self._horizontal_forward_direction(lens_origin)
        world_up: Vec3 = (0.0, 0.0, 1.0)
        if abs(vec_dot(lens_forward, world_up)) > 0.98:
            world_up = (0.0, 1.0, 0.0)
        lens_right = vec_normalize(vec_cross(lens_forward, world_up))
        if lens_right is None:
            return None
        lens_up = vec_cross(lens_right, lens_forward)
        return (lens_origin, lens_right, lens_up, lens_forward)

    def _effective_projector_fov_now(self) -> float:
        return self._effective_projector_fov_deg()

    def _effective_projector_fov_deg(self) -> float:
        if self.projector_fov_deg is not None:
            return max(1.1, min(179.0, self.projector_fov_deg))
        return self._default_projector_fov_deg

