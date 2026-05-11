from __future__ import annotations

import math

from PySide6.QtCore import QPointF

from ..core.constants import FIELD_OBJECT_PLANE_GAP_M
from ..core.math3d import vec_cross, vec_dot, vec_normalize, vec_subtract
from ..core.types import CameraContext, Vec3


class CameraNavigationMixin:
    def _surface_camera_view_context(
        self, viewport_width: int, viewport_height: int
    ) -> CameraContext | None:
        telecentric_origin = self._surface_telecentric_lens_center_world()
        if telecentric_origin is None:
            return None
        forward = self._horizontal_forward_direction(telecentric_origin)
        look_at = (
            telecentric_origin[0] + forward[0],
            telecentric_origin[1] + forward[1],
            telecentric_origin[2] + forward[2],
        )
        return self._camera_projection_context_for_viewport(
            telecentric_origin,
            look_at,
            viewport_width,
            viewport_height,
            self._effective_projector_fov_deg(),
        )

    def _plane_center(self) -> Vec3:
        delta = self.distance_m - self._base_distance_m
        d = self._plane_shift_direction
        return (
            self._base_plane_center[0] + d[0] * delta,
            self._base_plane_center[1] + d[1] * delta,
            self._base_plane_center[2] + d[2] * delta,
        )

    def _field_center(self) -> Vec3:
        frame = self._field_object_frame()
        if frame is None:
            return (self.field_center_x, self.field_center_y, self.field_center_z)
        plane_center, _, _, normal = frame
        offset = FIELD_OBJECT_PLANE_GAP_M + self._field_object_depth() * 0.5
        return (
            plane_center[0] + normal[0] * offset,
            plane_center[1] + normal[1] * offset,
            plane_center[2] + normal[2] * offset,
        )

    def _primary_projection_surface(self) -> tuple[Vec3, float, float] | None:
        if self.project_projection_plane:
            return (self._plane_center(), self.plane_width_m, self.plane_height_m)
        if self.project_field_object:
            return (self._field_center(), self.field_width_m, self.field_height_m)
        return None

    def _active_projection_centers(self) -> list[Vec3]:
        centers: list[Vec3] = []
        if self.project_projection_plane:
            centers.append(self._plane_center())
        if self.project_field_object:
            centers.append(self._field_center())
        if not centers:
            centers.append(self._plane_center())
        return centers

    def _look_target(self) -> Vec3:
        centers = self._active_projection_centers()
        count = float(len(centers))
        return (
            sum(c[0] for c in centers) / count,
            sum(c[1] for c in centers) / count,
            sum(c[2] for c in centers) / count,
        )

    def _sync_orbit_from_camera(self) -> None:
        offset = vec_subtract(
            (self.camera_x, self.camera_y, self.camera_z),
            self._orbit_target,
        )
        radius = math.sqrt(vec_dot(offset, offset))
        if radius <= 1e-6:
            radius = 1.0
            offset = (0.0, -1.0, 0.0)

        self._orbit_radius = radius
        self._orbit_azimuth = math.atan2(offset[1], offset[0])
        horizontal = math.sqrt(offset[0] * offset[0] + offset[1] * offset[1])
        self._orbit_elevation = math.atan2(offset[2], horizontal)

    def _apply_orbit_to_camera(self) -> None:
        cos_elevation = math.cos(self._orbit_elevation)
        tx, ty, tz = self._orbit_target
        self.camera_x = tx + self._orbit_radius * cos_elevation * math.cos(self._orbit_azimuth)
        self.camera_y = ty + self._orbit_radius * cos_elevation * math.sin(self._orbit_azimuth)
        self.camera_z = tz + self._orbit_radius * math.sin(self._orbit_elevation)

    def _rotate_plane_point(self, point: Vec3, plane_center: Vec3) -> Vec3:
        yaw = math.radians(self.yaw_deg)
        pitch = math.radians(self.pitch_deg)
        roll = math.radians(self.roll_deg)
        cyaw, syaw = math.cos(yaw), math.sin(yaw)
        cpitch, spitch = math.cos(pitch), math.sin(pitch)
        croll, sroll = math.cos(roll), math.sin(roll)

        x = point[0] - plane_center[0]
        y = point[1] - plane_center[1]
        z = point[2] - plane_center[2]

        # Rotation order: yaw(Z) -> pitch(X) -> roll(Y)
        x1, y1, z1 = (
            cyaw * x - syaw * y,
            syaw * x + cyaw * y,
            z,
        )
        x2, y2, z2 = (
            x1,
            cpitch * y1 - spitch * z1,
            spitch * y1 + cpitch * z1,
        )
        x3, y3, z3 = (
            croll * x2 + sroll * z2,
            y2,
            -sroll * x2 + croll * z2,
        )
        return (
            x3 + plane_center[0],
            y3 + plane_center[1],
            z3 + plane_center[2],
        )

    def _camera_projection_context(
        self, viewport_width: int, viewport_height: int
    ) -> CameraContext | None:
        return self._camera_projection_context_for_viewport(
            (self.camera_x, self.camera_y, self.camera_z),
            self._orbit_target,
            viewport_width,
            viewport_height,
            self.fov_deg,
        )

    def _camera_projection_context_for_viewport(
        self,
        camera: Vec3,
        look_at: Vec3,
        viewport_width: int,
        viewport_height: int,
        fov_deg: float,
    ) -> CameraContext | None:
        world_up: Vec3 = (0.0, 0.0, 1.0)

        forward = vec_normalize(vec_subtract(look_at, camera))
        if forward is None:
            return None
        if abs(vec_dot(forward, world_up)) > 0.98:
            world_up = (0.0, 1.0, 0.0)
        right = vec_normalize(vec_cross(forward, world_up))
        if right is None:
            return None
        up = vec_cross(right, forward)

        focal = (viewport_height / 2.0) / math.tan(math.radians(fov_deg) / 2.0)
        cx = viewport_width / 2.0
        cy_screen = viewport_height / 2.0
        return (camera, right, up, forward, focal, cx, cy_screen)

    def _world_to_camera(
        self,
        world_point: Vec3,
        context: CameraContext,
    ) -> Vec3:
        camera, right, up, forward, _, _, _ = context
        rel = vec_subtract(world_point, camera)
        return (vec_dot(rel, right), vec_dot(rel, up), vec_dot(rel, forward))

    def _project_camera_point(
        self,
        camera_point: Vec3,
        context: CameraContext,
    ) -> QPointF | None:
        _, _, _, _, focal, cx, cy_screen = context
        x_cam, y_cam, z_cam = camera_point
        if z_cam <= 1e-6:
            return None
        sx = cx + (focal * x_cam / z_cam)
        sy = cy_screen - (focal * y_cam / z_cam)
        return QPointF(sx, sy)

    def _project_world_point(
        self,
        world_point: Vec3,
        context: CameraContext,
    ) -> QPointF | None:
        camera_point = self._world_to_camera(world_point, context)
        return self._project_camera_point(camera_point, context)

    def _project_segment_clipped(
        self,
        start: Vec3,
        end: Vec3,
        context: CameraContext,
    ) -> tuple[QPointF, QPointF] | None:
        near = 1e-3
        a = self._world_to_camera(start, context)
        b = self._world_to_camera(end, context)

        if a[2] <= near and b[2] <= near:
            return None
        if a[2] <= near or b[2] <= near:
            az = a[2]
            bz = b[2]
            if abs(bz - az) <= 1e-9:
                return None
            t = (near - az) / (bz - az)
            intersection = (
                a[0] + t * (b[0] - a[0]),
                a[1] + t * (b[1] - a[1]),
                near,
            )
            if a[2] <= near:
                a = intersection
            else:
                b = intersection

        pa = self._project_camera_point(a, context)
        pb = self._project_camera_point(b, context)
        if pa is None or pb is None:
            return None
        return (pa, pb)

