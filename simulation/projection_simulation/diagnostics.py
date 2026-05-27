from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .core.constants import (
    PROJECTOR_LENS_HEIGHT_CM,
    SURFACE_CAMERA_CAPTURE_HEIGHT_PX,
    SURFACE_CAMERA_CAPTURE_WIDTH_PX,
    SURFACE_CAMERA_MODEL,
    SURFACE_CAMERA_PIXEL_PITCH_UM,
    SURFACE_CAMERA_LENS_HEIGHT_CM,
    SURFACE_CAMERA_SENSOR_HEIGHT_PX,
    SURFACE_CAMERA_SENSOR_HEIGHT_MM,
    SURFACE_CAMERA_SENSOR_MODEL,
    SURFACE_CAMERA_SENSOR_WIDTH_PX,
    SURFACE_CAMERA_SENSOR_WIDTH_MM,
    TELECENTRIC_LENS_DIAMETER_CM,
)
from .core.math3d import vec_dot, vec_subtract
from .core.types import Vec3

if TYPE_CHECKING:
    from .ui.window import ProjectionWindow


def run_optics_smoke_checks(window: ProjectionWindow) -> list[str]:
    messages: list[str] = []
    width = SURFACE_CAMERA_SENSOR_WIDTH_PX
    height = SURFACE_CAMERA_SENSOR_HEIGHT_PX

    native = _require_scan_context(window, width, height)
    half = _require_scan_context(window, width // 2, height // 2)
    arbitrary = _require_scan_context(window, 1920, 1080)
    default_capture = _require_scan_context(
        window,
        SURFACE_CAMERA_CAPTURE_WIDTH_PX,
        SURFACE_CAMERA_CAPTURE_HEIGHT_PX,
    )
    _assert_close("telecentric half-width is capture-size invariant", native[4], half[4])
    _assert_close("telecentric half-height is capture-size invariant", native[5], half[5])
    _assert_close("telecentric half-width is arbitrary-size invariant", native[4], arbitrary[4])
    _assert_close("telecentric half-height is arbitrary-size invariant", native[5], arbitrary[5])
    _assert_close("telecentric half-width is default-capture invariant", native[4], default_capture[4])
    _assert_close("telecentric half-height is default-capture invariant", native[5], default_capture[5])
    messages.append(
        f"telecentric field is capture-size invariant: {native[4] * 2.0:.4f} x {native[5] * 2.0:.4f} cm"
    )
    messages.append(
        f"{SURFACE_CAMERA_MODEL} uses {SURFACE_CAMERA_SENSOR_MODEL} geometry: "
        f"{SURFACE_CAMERA_SENSOR_WIDTH_PX}x{SURFACE_CAMERA_SENSOR_HEIGHT_PX}px, "
        f"{SURFACE_CAMERA_PIXEL_PITCH_UM:.2f} um pitch, "
        f"{SURFACE_CAMERA_SENSOR_WIDTH_MM:.4f}x{SURFACE_CAMERA_SENSOR_HEIGHT_MM:.4f} mm sensor"
    )

    expected_aspect = SURFACE_CAMERA_SENSOR_WIDTH_PX / SURFACE_CAMERA_SENSOR_HEIGHT_PX
    _assert_close("telecentric field matches native sensor aspect", native[4] / native[5], expected_aspect)
    aperture_radius = TELECENTRIC_LENS_DIAMETER_CM * 0.5
    if math.hypot(native[4], native[5]) > aperture_radius + 1e-9:
        raise ValueError("Telecentric sensor rectangle exceeds front aperture radius.")
    messages.append("native Blackfly sensor field is inscribed inside the 10.0 cm telecentric aperture")

    original_fov = window.projector_fov_deg
    try:
        window.projector_fov_deg = 30.0
        low_fov = _require_scan_context(window, width, height)
        window.projector_fov_deg = 120.0
        high_fov = _require_scan_context(window, width, height)
    finally:
        window.projector_fov_deg = original_fov
    _assert_close("projector FOV does not affect telecentric half-width", low_fov[4], high_fov[4])
    _assert_close("projector FOV does not affect telecentric half-height", low_fov[5], high_fov[5])
    messages.append("projector FOV is decoupled from telecentric camera field")

    near_span = _telecentric_pixel_span_at_depth(window, native, width, height, 5.0)
    far_span = _telecentric_pixel_span_at_depth(window, native, width, height, 25.0)
    _assert_close("telecentric scale is depth-invariant", near_span, far_span)
    messages.append(f"telecentric scale is depth-invariant: sample span {near_span:.6f} cm")

    telecentric_center = window._surface_telecentric_lens_center_world()
    projector_center = window._projector_projection_origin_world()
    if telecentric_center is None or projector_center is None:
        raise ValueError("Optical centers could not be resolved.")
    _assert_close("telecentric optical center height", telecentric_center[2], SURFACE_CAMERA_LENS_HEIGHT_CM)
    _assert_close("projector optical center height", projector_center[2], PROJECTOR_LENS_HEIGHT_CM)
    messages.append(
        f"optical centers are on the configured axis: camera z={telecentric_center[2]:.4f} cm, projector z={projector_center[2]:.4f} cm"
    )
    return messages


def _require_scan_context(
    window: ProjectionWindow,
    width: int,
    height: int,
) -> tuple[Vec3, Vec3, Vec3, Vec3, float, float]:
    context = window._surface_camera_telecentric_scan_context(width, height)
    if context is None:
        raise ValueError(f"Could not create telecentric scan context for {width}x{height}.")
    return context


def _telecentric_pixel_span_at_depth(
    window: ProjectionWindow,
    context: tuple[Vec3, Vec3, Vec3, Vec3, float, float],
    width: int,
    height: int,
    depth_cm: float,
) -> float:
    origin, _, _, forward, _, _ = context
    left_origin = window._telecentric_ray_origin(width * 0.25, height * 0.5, width, height, context)
    right_origin = window._telecentric_ray_origin(width * 0.75, height * 0.5, width, height, context)
    if left_origin is None or right_origin is None:
        raise ValueError("Could not resolve telecentric sample rays.")
    plane_point = (
        origin[0] + forward[0] * depth_cm,
        origin[1] + forward[1] * depth_cm,
        origin[2] + forward[2] * depth_cm,
    )
    left_hit = window._intersect_ray_with_plane(left_origin, forward, plane_point, forward)
    right_hit = window._intersect_ray_with_plane(right_origin, forward, plane_point, forward)
    if left_hit is None or right_hit is None:
        raise ValueError("Could not intersect telecentric rays with depth plane.")
    delta = vec_subtract(right_hit, left_hit)
    return math.sqrt(vec_dot(delta, delta))


def _assert_close(name: str, actual: float, expected: float, tolerance: float = 1e-9) -> None:
    if abs(actual - expected) > tolerance:
        raise ValueError(f"{name}: expected {expected:.12g}, got {actual:.12g}.")
