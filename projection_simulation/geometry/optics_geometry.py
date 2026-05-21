from __future__ import annotations

import math

from ..core.constants import (
    DEFAULT_DEVICE_SPACING_CM,
    DEFAULT_PROJECTION_ANGLE_DEG,
    PROJECTOR_ANGLE_LIMIT_DEG,
    PROJECTOR_IMAGE_ASPECT,
    PROJECTOR_LENS_HEIGHT_CM,
    PROJECTOR_THROW_RATIO,
    SURFACE_CAMERA_LENS_HEIGHT_CM,
    TELECENTRIC_LENS_TO_CAMERA_LENS_CM,
)
from ..core.math3d import vec_cross, vec_dot, vec_normalize, vec_subtract
from ..core.types import Vec3


class OpticsGeometryMixin:
    def _projector_projection_origin_world(self) -> Vec3 | None:
        lens_data = self._projector_lens_rectangle_world()
        if lens_data is None:
            return None
        _, projector_origin = lens_data
        return projector_origin

    def _resolve_base_plane_center(self, distance_m: float) -> Vec3:
        if self.use_axis_distance:
            if self.projector_axis == "y":
                return (
                    self.projector_x,
                    self.projector_y + distance_m,
                    self.projector_z,
                )
            return (
                self.projector_x,
                self.projector_y,
                self.projector_z + distance_m,
            )
        return (
            self.plane_center_x,
            self.plane_center_y,
            self.plane_center_z,
        )

    def _derive_symmetry_basis(self) -> tuple[Vec3, Vec3]:
        center = self._base_plane_center
        projector = (self.projector_x, self.projector_y, self.projector_z)
        surface_camera = (self.main_camera_x, self.main_camera_y, self.main_camera_z)
        midpoint = (
            (projector[0] + surface_camera[0]) * 0.5,
            (projector[1] + surface_camera[1]) * 0.5,
            (projector[2] + surface_camera[2]) * 0.5,
        )

        normal = vec_normalize(vec_subtract(midpoint, center))
        if normal is None:
            normal = vec_normalize(vec_subtract(projector, center))
        if normal is None:
            normal = (0.0, -1.0, 0.0) if self.projector_axis == "y" else (0.0, 0.0, -1.0)

        tangent_raw = vec_subtract(surface_camera, projector)
        tangent_planar = (
            tangent_raw[0] - normal[0] * vec_dot(tangent_raw, normal),
            tangent_raw[1] - normal[1] * vec_dot(tangent_raw, normal),
            tangent_raw[2] - normal[2] * vec_dot(tangent_raw, normal),
        )
        tangent = vec_normalize(tangent_planar)
        if tangent is None:
            world_up: Vec3 = (0.0, 0.0, 1.0)
            tangent = vec_normalize(vec_cross(world_up, normal))
        if tangent is None:
            tangent = (1.0, 0.0, 0.0)
        return (normal, tangent)

    def _derive_initial_projection_geometry(
        self, configured_distance_cm: float
    ) -> tuple[float, float]:
        angle = max(
            -float(PROJECTOR_ANGLE_LIMIT_DEG),
            min(float(PROJECTOR_ANGLE_LIMIT_DEG), DEFAULT_PROJECTION_ANGLE_DEG),
        )
        return (angle, max(0.2, configured_distance_cm))

    def _spacing_from_angle(self, angle_deg: float, radius_cm: float) -> float:
        if radius_cm <= 1e-9:
            return 0.0
        return abs(2.0 * radius_cm * math.sin(math.radians(angle_deg)))

    def _clamp_aperture_center_world(self, origin: Vec3) -> Vec3 | None:
        """Return the front telecentric aperture center on the optical-axis height."""
        forward = self._horizontal_forward_direction(origin)
        world_up: Vec3 = (0.0, 0.0, 1.0)
        if abs(vec_dot(forward, world_up)) > 0.98:
            world_up = (0.0, 1.0, 0.0)
        right = vec_normalize(vec_cross(world_up, forward))
        if right is None:
            return None
        up = vec_cross(forward, right)
        if abs(up[2]) <= 1e-6:
            return None
        ground_align_local_y = -origin[2] / up[2]
        hole_center_y = SURFACE_CAMERA_LENS_HEIGHT_CM
        return (
            origin[0] + up[0] * (hole_center_y + ground_align_local_y),
            origin[1] + up[1] * (hole_center_y + ground_align_local_y),
            origin[2] + up[2] * (hole_center_y + ground_align_local_y),
        )

    def _surface_telecentric_lens_center_world(self) -> Vec3 | None:
        return self._clamp_aperture_center_world(self._surface_camera_pos)

    def _surface_camera_lens_centers_world(self) -> tuple[Vec3, Vec3, Vec3] | None:
        telecentric_center = self._surface_telecentric_lens_center_world()
        if telecentric_center is None:
            return None
        forward = self._horizontal_forward_direction(telecentric_center)
        camera_lens_center = (
            telecentric_center[0] - forward[0] * TELECENTRIC_LENS_TO_CAMERA_LENS_CM,
            telecentric_center[1] - forward[1] * TELECENTRIC_LENS_TO_CAMERA_LENS_CM,
            telecentric_center[2] - forward[2] * TELECENTRIC_LENS_TO_CAMERA_LENS_CM,
        )
        return (telecentric_center, camera_lens_center, forward)

    def _ray_origins_world(self) -> tuple[Vec3, Vec3] | None:
        projector_origin = self._projector_projection_origin_world()
        if projector_origin is None:
            return None
        lens_centers = self._surface_camera_lens_centers_world()
        if lens_centers is None:
            return None
        telecentric_origin, _, _ = lens_centers
        return (projector_origin, telecentric_origin)

    def _ray_angle_to_y_axis_deg(self, direction: Vec3 | None) -> float | None:
        if direction is None:
            return None
        planar = vec_normalize((direction[0], direction[1], 0.0))
        if planar is None:
            return None
        y_axis: Vec3 = (0.0, 1.0, 0.0)
        dot = max(-1.0, min(1.0, vec_dot(planar, y_axis)))
        return math.degrees(math.acos(dot))

    def _projector_ray_angle_to_y_axis_deg(self) -> float | None:
        axes = self._projector_axes()
        if axes is None:
            return None
        return self._ray_angle_to_y_axis_deg(axes[3])

    def _clamp_ray_angle_to_y_axis_deg(self) -> float | None:
        telecentric_origin = self._surface_telecentric_lens_center_world()
        if telecentric_origin is None:
            return None
        return self._ray_angle_to_y_axis_deg(self._horizontal_forward_direction(telecentric_origin))

    def _update_reflected_devices(self) -> None:
        if not hasattr(self, "_device_lateral_sign"):
            self._device_lateral_sign = -1.0 if self._projection_angle_deg < 0.0 else 1.0
        if not hasattr(self, "_device_spacing_cm"):
            self._device_spacing_cm = DEFAULT_DEVICE_SPACING_CM
        center = self._base_plane_center
        half_spacing = max(0.0, self._device_spacing_cm * 0.5)
        max_half_spacing = max(0.0, self._device_distance_m)
        half_spacing = min(half_spacing, max_half_spacing)
        normal_offset = math.sqrt(
            max(0.0, self._device_distance_m * self._device_distance_m - half_spacing * half_spacing)
        )
        lateral_offset = half_spacing * self._device_lateral_sign
        if self._device_distance_m > 1e-9:
            ratio = max(-1.0, min(1.0, lateral_offset / self._device_distance_m))
            self._projection_angle_deg = math.degrees(math.asin(ratio))
        else:
            self._projection_angle_deg = 0.0
        n = self._symmetry_normal
        t = self._symmetry_tangent
        self._projector_pos = (
            center[0] + n[0] * normal_offset + t[0] * lateral_offset,
            center[1] + n[1] * normal_offset + t[1] * lateral_offset,
            center[2] + n[2] * normal_offset + t[2] * lateral_offset,
        )
        self._surface_camera_pos = (
            center[0] + n[0] * normal_offset - t[0] * lateral_offset,
            center[1] + n[1] * normal_offset - t[1] * lateral_offset,
            center[2] + n[2] * normal_offset - t[2] * lateral_offset,
        )
        # Reposition device bodies until their optical origins, not chassis
        # origins, satisfy the requested symmetry and spacing constraints.
        for _ in range(20):
            self._align_projector_lens_to_optical_axis()
            self._align_ray_starts_to_x_axis()
            self._enforce_ray_origin_spacing()

    def _align_projector_lens_to_optical_axis(self) -> None:
        lens_data = self._projector_lens_rectangle_world()
        if lens_data is None:
            return
        _, lens_center = lens_data
        delta_z = PROJECTOR_LENS_HEIGHT_CM - lens_center[2]
        if abs(delta_z) <= 1e-6:
            return
        self._projector_pos = (
            self._projector_pos[0],
            self._projector_pos[1],
            self._projector_pos[2] + delta_z,
        )

    def _align_ray_starts_to_x_axis(self) -> None:
        for _ in range(4):
            clamp_origin = self._surface_telecentric_lens_center_world()
            if clamp_origin is not None:
                clamp_delta_y = -clamp_origin[1]
                if abs(clamp_delta_y) > 1e-6:
                    self._surface_camera_pos = (
                        self._surface_camera_pos[0],
                        self._surface_camera_pos[1] + clamp_delta_y,
                        self._surface_camera_pos[2],
                    )
            lens_data = self._projector_lens_rectangle_world()
            if lens_data is None:
                break
            _, lens_center = lens_data
            delta_y = -lens_center[1]
            if abs(delta_y) <= 1e-6:
                break
            self._projector_pos = (
                self._projector_pos[0],
                self._projector_pos[1] + delta_y,
                self._projector_pos[2],
            )

    def _enforce_ray_origin_spacing(self) -> None:
        if not hasattr(self, "_device_spacing_cm"):
            return
        origins = self._ray_origins_world()
        if origins is None:
            return
        projector_origin, clamp_origin = origins
        half_spacing = max(0.0, self._device_spacing_cm * 0.5)
        target_projector_x = half_spacing
        target_clamp_x = -half_spacing
        projector_dx = target_projector_x - projector_origin[0]
        clamp_dx = target_clamp_x - clamp_origin[0]
        if abs(projector_dx) > 1e-6:
            self._projector_pos = (
                self._projector_pos[0] + projector_dx,
                self._projector_pos[1],
                self._projector_pos[2],
            )
        if abs(clamp_dx) > 1e-6:
            self._surface_camera_pos = (
                self._surface_camera_pos[0] + clamp_dx,
                self._surface_camera_pos[1],
                self._surface_camera_pos[2],
            )

    def _compute_default_projector_fov_deg(self) -> float:
        half_h = math.atan(0.5 / PROJECTOR_THROW_RATIO)
        half_v = math.atan(math.tan(half_h) / PROJECTOR_IMAGE_ASPECT)
        return math.degrees(half_v * 2.0)

