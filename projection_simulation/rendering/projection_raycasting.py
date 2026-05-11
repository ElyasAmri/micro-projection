from __future__ import annotations

from PySide6.QtGui import QColor

from ..core.math3d import vec_cross, vec_dot, vec_normalize, vec_subtract
from ..core.types import Vec3

SceneSurface = tuple[str, list[Vec3], QColor]
TelecentricScanContext = tuple[Vec3, Vec3, Vec3, Vec3, float, float]


class ProjectionRaycastingMixin:
    def _ray_surface_intersection(
        self,
        ray_origin: Vec3,
        ray_direction: Vec3,
        surface: list[Vec3],
    ) -> tuple[float, Vec3] | None:
        with self._profile_section("_ray_surface_intersection"):
            if len(surface) < 3:
                return None
            edge_u = vec_subtract(surface[1], surface[0])
            edge_v = vec_subtract(surface[-1], surface[0])
            normal = vec_normalize(vec_cross(edge_u, edge_v))
            if normal is None:
                return None

            denominator = vec_dot(ray_direction, normal)
            if abs(denominator) <= 1e-8:
                return None
            ray_to_plane = vec_subtract(surface[0], ray_origin)
            distance = vec_dot(ray_to_plane, normal) / denominator
            if distance <= 1e-5:
                return None

            hit = (
                ray_origin[0] + ray_direction[0] * distance,
                ray_origin[1] + ray_direction[1] * distance,
                ray_origin[2] + ray_direction[2] * distance,
            )
            edge_signs: list[float] = []
            for index, corner in enumerate(surface):
                next_corner = surface[(index + 1) % len(surface)]
                edge = vec_subtract(next_corner, corner)
                to_hit = vec_subtract(hit, corner)
                edge_signs.append(vec_dot(vec_cross(edge, to_hit), normal))
            if not (
                all(sign >= -1e-6 for sign in edge_signs)
                or all(sign <= 1e-6 for sign in edge_signs)
            ):
                return None
            return (distance, hit)

    def _first_projector_hit(
        self,
        x_pixel: float,
        y_pixel: float,
        image_width: int,
        image_height: int,
        projector_context: tuple[Vec3, Vec3, Vec3, Vec3, float, float],
        surfaces: list[SceneSurface],
    ) -> tuple[int, Vec3] | None:
        with self._profile_section("_first_projector_hit"):
            ray_direction = self._projector_ray_direction(
                x_pixel,
                y_pixel,
                image_width,
                image_height,
                projector_context,
            )
            if ray_direction is None:
                return None

            projector_origin = projector_context[0]
            nearest: tuple[float, int, Vec3] | None = None
            for surface_index, (_, corners, _) in enumerate(surfaces):
                intersection = self._ray_surface_intersection(
                    projector_origin,
                    ray_direction,
                    corners,
                )
                if intersection is None:
                    continue
                distance, hit = intersection
                if nearest is None or distance < nearest[0]:
                    nearest = (distance, surface_index, hit)
            if nearest is None:
                return None
            return (nearest[1], nearest[2])

    def _first_telecentric_scan_hit(
        self,
        x_pixel: float,
        y_pixel: float,
        image_width: int,
        image_height: int,
        scan_context: TelecentricScanContext,
        surfaces: list[SceneSurface],
    ) -> tuple[int, Vec3] | None:
        with self._profile_section("_first_telecentric_scan_hit"):
            if image_width <= 0 or image_height <= 0:
                return None
            origin, right, up, forward, half_w, half_h = scan_context
            nx = (2.0 * x_pixel / float(image_width)) - 1.0
            ny = 1.0 - (2.0 * y_pixel / float(image_height))
            ray_origin = (
                origin[0] + right[0] * (nx * half_w) + up[0] * (ny * half_h),
                origin[1] + right[1] * (nx * half_w) + up[1] * (ny * half_h),
                origin[2] + right[2] * (nx * half_w) + up[2] * (ny * half_h),
            )
            nearest: tuple[float, int, Vec3] | None = None
            for surface_index, (_, corners, _) in enumerate(surfaces):
                intersection = self._ray_surface_intersection(ray_origin, forward, corners)
                if intersection is None:
                    continue
                distance, hit = intersection
                if nearest is None or distance < nearest[0]:
                    nearest = (distance, surface_index, hit)
            if nearest is None:
                return None
            return (nearest[1], nearest[2])

    def _telecentric_ray_origin(
        self,
        x_pixel: float,
        y_pixel: float,
        image_width: int,
        image_height: int,
        scan_context: TelecentricScanContext,
    ) -> Vec3 | None:
        if image_width <= 0 or image_height <= 0:
            return None
        origin, right, up, _, half_w, half_h = scan_context
        nx = (2.0 * x_pixel / float(image_width)) - 1.0
        ny = 1.0 - (2.0 * y_pixel / float(image_height))
        return (
            origin[0] + right[0] * (nx * half_w) + up[0] * (ny * half_h),
            origin[1] + right[1] * (nx * half_w) + up[1] * (ny * half_h),
            origin[2] + right[2] * (nx * half_w) + up[2] * (ny * half_h),
        )

    def _projector_ray_direction(
        self,
        x_pixel: float,
        y_pixel: float,
        image_width: int,
        image_height: int,
        projector_context: tuple[Vec3, Vec3, Vec3, Vec3, float, float],
    ) -> Vec3 | None:
        origin, right, up, forward, tan_half_fov, aspect = projector_context
        nx = (2.0 * x_pixel / float(image_width)) - 1.0
        ny = 1.0 - (2.0 * y_pixel / float(image_height))
        direction = (
            forward[0] + right[0] * (nx * aspect * tan_half_fov) + up[0] * (ny * tan_half_fov),
            forward[1] + right[1] * (nx * aspect * tan_half_fov) + up[1] * (ny * tan_half_fov),
            forward[2] + right[2] * (nx * aspect * tan_half_fov) + up[2] * (ny * tan_half_fov),
        )
        return vec_normalize(direction)

    def _intersect_ray_with_plane(
        self,
        ray_origin: Vec3,
        ray_direction: Vec3,
        plane_point: Vec3,
        plane_normal: Vec3,
    ) -> Vec3 | None:
        denominator = vec_dot(ray_direction, plane_normal)
        if abs(denominator) <= 1e-8:
            return None
        ray_to_plane = vec_subtract(plane_point, ray_origin)
        t = vec_dot(ray_to_plane, plane_normal) / denominator
        if t <= 1e-5:
            return None
        return (
            ray_origin[0] + ray_direction[0] * t,
            ray_origin[1] + ray_direction[1] * t,
            ray_origin[2] + ray_direction[2] * t,
        )
