"""Rig geometry: world <-> projector/camera transforms.

Pure-math helpers that consume the metadata.json produced by
`blender/blender_projector_capture.py`. Used by the solver and the recording
pipeline.
"""
from __future__ import annotations

import numpy as np


def normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        raise ValueError("Cannot normalize zero-length vector.")
    return vector / norm


def matrix_from_rows(rows: object) -> np.ndarray:
    matrix = np.asarray(rows, dtype=np.float64)
    if matrix.shape != (4, 4):
        raise ValueError("Expected a 4x4 transform matrix in metadata.")
    return matrix


def frame_bounds_from_metadata(
    metadata: dict[str, object], key: str
) -> tuple[float, float, float, float, float]:
    values = np.asarray(metadata[key], dtype=np.float64)
    if values.shape != (5,):
        raise ValueError(f"Expected five frame-bound values in metadata key '{key}'.")
    return (
        float(values[0]),
        float(values[1]),
        float(values[2]),
        float(values[3]),
        float(values[4]),
    )


def transform_point(matrix_world: np.ndarray, point: np.ndarray) -> np.ndarray:
    homogeneous = np.append(np.asarray(point, dtype=np.float64), 1.0)
    return (matrix_world @ homogeneous)[:3]


def transform_direction(matrix_world: np.ndarray, direction: np.ndarray) -> np.ndarray:
    return matrix_world[:3, :3] @ np.asarray(direction, dtype=np.float64)


def plane_geometry(
    metadata: dict[str, object],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(centre, right, up, normal) of the projection plane in world coordinates."""
    plane_matrix = matrix_from_rows(metadata["plane_matrix_world"])
    plane_center = transform_point(plane_matrix, np.array([0.0, 0.0, 0.0], dtype=np.float64))
    plane_right = normalize(transform_direction(plane_matrix, np.array([1.0, 0.0, 0.0], dtype=np.float64)))
    plane_up = normalize(transform_direction(plane_matrix, np.array([0.0, 1.0, 0.0], dtype=np.float64)))
    plane_normal = normalize(transform_direction(plane_matrix, np.array([0.0, 0.0, 1.0], dtype=np.float64)))
    return plane_center, plane_right, plane_up, plane_normal


def project_world_to_projector_x(world_point: np.ndarray, metadata: dict[str, object]) -> float:
    """Projector column (pixel coordinate, -0.5 offset) for a single world point."""
    projector_matrix = matrix_from_rows(metadata["projector_matrix_world"])
    projector_world_to_local = np.linalg.inv(projector_matrix)
    local_point = transform_point(projector_world_to_local, world_point)
    min_x, max_x, _, _, frame_z = frame_bounds_from_metadata(metadata, "projector_frame_bounds_local")
    if abs(float(local_point[2])) <= 1e-12:
        raise ValueError("World point lies on the projector origin plane.")
    projected_frame_x = float(local_point[0] * (frame_z / local_point[2]))
    normalized = (projected_frame_x - min_x) / (max_x - min_x)
    return normalized * int(metadata["fringe_width"]) - 0.5


def projector_x_from_world_points(points: np.ndarray, metadata: dict[str, object]) -> np.ndarray:
    """Vectorized projector-column for an array of world points (last axis == 3)."""
    projector_matrix = matrix_from_rows(metadata["projector_matrix_world"])
    projector_world_to_local = np.linalg.inv(projector_matrix)
    min_x, max_x, _, _, frame_z = frame_bounds_from_metadata(metadata, "projector_frame_bounds_local")
    fringe_width = float(metadata["fringe_width"])
    homogeneous = np.concatenate(
        [np.asarray(points, dtype=np.float64), np.ones((*points.shape[:-1], 1), dtype=np.float64)],
        axis=-1,
    )
    local = homogeneous @ projector_world_to_local.T
    frame_x = local[..., 0] * (frame_z / local[..., 2])
    normalized = (frame_x - min_x) / (max_x - min_x)
    return normalized * fringe_width - 0.5


def fringe_pitch_mm(metadata: dict[str, object], period_proj_px: float) -> float:
    """Physical pitch of one fringe period on the reference plane, in mm.

    Converts the device-native projector-pixel period to a real-world distance on
    the measurement plane (view-independent), via the projector frustum geometry.
    """
    plane_center, plane_right, _, _ = plane_geometry(metadata)
    probe_m = 0.05
    x0 = project_world_to_projector_x(plane_center, metadata)
    x1 = project_world_to_projector_x(plane_center + plane_right * probe_m, metadata)
    mm_per_projector_px = (probe_m * 1000.0) / abs(x1 - x0)
    return period_proj_px * mm_per_projector_px


def projector_column_plane(
    metadata: dict[str, object],
    projector_x: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Plane (centre, normal) that contains every world point projecting to one
    projector column. Used to triangulate from a known phase."""
    projector_matrix = matrix_from_rows(metadata["projector_matrix_world"])
    projector_center = transform_point(projector_matrix, np.array([0.0, 0.0, 0.0], dtype=np.float64))
    min_x, max_x, min_y, max_y, frame_z = frame_bounds_from_metadata(metadata, "projector_frame_bounds_local")
    projector_width = int(metadata["fringe_width"])
    normalized = (projector_x + 0.5) / projector_width
    local_x = min_x + (max_x - min_x) * normalized
    bottom_point = transform_point(projector_matrix, np.array([local_x, min_y, frame_z], dtype=np.float64))
    top_point = transform_point(projector_matrix, np.array([local_x, max_y, frame_z], dtype=np.float64))
    plane_normal = normalize(np.cross(bottom_point - projector_center, top_point - projector_center))
    return projector_center, plane_normal


def capture_rays_from_pixels(
    metadata: dict[str, object],
    xs: np.ndarray,
    ys: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-pixel ray origins plus the single shared ray direction.

    The capture camera is orthographic, so every ray shares one direction and only
    the origin varies across the sensor - the whole pixel grid resolves in one
    vectorized transform instead of a Python loop.
    """
    width = int(metadata["render_width"])
    height = int(metadata["render_height"])
    min_x, max_x, min_y, max_y, _ = frame_bounds_from_metadata(metadata, "capture_camera_frame_bounds_local")
    camera_matrix = matrix_from_rows(metadata["capture_camera_matrix_world"])
    nx = (np.asarray(xs, dtype=np.float64) + 0.5) / width
    ny = 1.0 - ((np.asarray(ys, dtype=np.float64) + 0.5) / height)
    local = np.stack(
        [min_x + (max_x - min_x) * nx, min_y + (max_y - min_y) * ny, np.zeros_like(nx)],
        axis=1,
    )
    origins = local @ camera_matrix[:3, :3].T + camera_matrix[:3, 3]
    direction = normalize(transform_direction(camera_matrix, np.array([0.0, 0.0, -1.0], dtype=np.float64)))
    return origins, direction
