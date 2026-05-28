"""Multi-frequency photometric depth solver: PSA per period, temporal unwrap, direct depth."""
from __future__ import annotations

import math

import numpy as np

from geometry import (
    capture_rays_from_pixels,
    plane_geometry,
    projector_x_from_world_points,
)
from reconstruction import (
    phase_shift_sequence,
    unwrap_phase_2d,
    wrapped_phase_delta,
)


def psa_height_delta(
    object_frames: np.ndarray,
    reference_frames: np.ndarray,
    count: int,
    phase_steps_rad: np.ndarray,
) -> np.ndarray:
    """Carrier-removed wrapped height phase from the first ``count`` captures."""
    steps = phase_steps_rad[:count]
    measured = phase_shift_sequence(object_frames[:count], phase_steps_rad=steps)
    reference = phase_shift_sequence(reference_frames[:count], phase_steps_rad=steps)
    return wrapped_phase_delta(measured.wrapped_phase, reference.wrapped_phase)


def absolute_height_phase(
    deltas: list[np.ndarray],
    periods_coarse_to_fine: list[float],
    mask: np.ndarray,
) -> np.ndarray:
    """Multi-frequency temporal unwrap of coarse->fine wrapped height deltas."""
    absolute = np.zeros_like(deltas[0])
    absolute[mask] = unwrap_phase_2d(deltas[0])[mask]
    previous_period = periods_coarse_to_fine[0]
    for delta, period in zip(deltas[1:], periods_coarse_to_fine[1:]):
        expected = absolute * (previous_period / period)
        wraps = np.round((expected - delta) / (2.0 * math.pi))
        absolute = delta + (2.0 * math.pi) * wraps
        previous_period = period
    return absolute


def reference_projector_x_map(
    metadata: dict[str, object],
    valid_mask: np.ndarray,
) -> np.ndarray:
    """Projector-x coordinate of each valid pixel's intersection with the plane."""
    plane_center, _, _, plane_normal = plane_geometry(metadata)
    projector_x = np.full(valid_mask.shape, np.nan, dtype=np.float64)
    ys, xs = np.where(valid_mask)
    if xs.size == 0:
        return projector_x
    origins, direction = capture_rays_from_pixels(metadata, xs, ys)
    denominator = float(np.dot(direction, plane_normal))
    if abs(denominator) <= 1e-12:
        return projector_x
    distance = (plane_center - origins) @ plane_normal / denominator
    hits = origins + distance[:, None] * direction[None, :]
    good = distance > 1e-9
    if np.any(good):
        projector_x[ys[good], xs[good]] = projector_x_from_world_points(hits[good], metadata)
    return projector_x


def prepare_camera_ray_geometry(
    metadata: dict[str, object],
    mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Per-valid-pixel plane intersection + ray-coefficient for `mask`.

    Returns (ys, xs, plane_hits, ray_coefficients). `plane_hits[i]` is the
    point at which pixel (ys[i], xs[i])'s ray meets the reference plane, and
    `ray_coefficients[i] = direction / (direction . plane_normal)` so that
    `plane_hits + depth * ray_coefficients` is the world point at signed
    height `depth`.
    """
    plane_center, _, _, plane_normal = plane_geometry(metadata)
    ys, xs = np.where(mask)
    origins, direction = capture_rays_from_pixels(metadata, xs, ys)
    denominator = float(np.dot(direction, plane_normal))
    plane_t = (plane_center - origins) @ plane_normal / denominator
    plane_hits = origins + plane_t[:, None] * direction[None, :]
    ray_coefficients = np.broadcast_to(direction / denominator, origins.shape).copy()
    return ys, xs, plane_hits, ray_coefficients


def direct_photometric_depth_solve(
    metadata: dict[str, object],
    mask: np.ndarray,
    object_sequences: list[np.ndarray],
    phase_steps_rad: list[np.ndarray],
    fringe_periods_px: list[float],
    *,
    reference_sequences: list[np.ndarray] | None = None,
    reference_projector_x: np.ndarray | None = None,
    max_depth_m: float = 0.025,
    coarse_step_m: float = 0.0001,
    fine_half_window_m: float = 0.0002,
    fine_step_m: float = 0.000005,
    chunk_size: int = 512,
    coarse_candidate_count: int = 1,
    quadratic_subsample: bool = False,
) -> tuple[np.ndarray, dict[str, float | int]]:
    """Coarse-then-fine photometric depth solver, vectorised over pixel chunks.

    Returns (reconstructed_height_map, solver_stats). The cost basis is
    `0.5 + 0.5*sin(2*pi/P * projector_x + delta)` per frequency, matching the
    fringe generator used by `blender/blender_projector_capture.py`.
    """
    if not object_sequences:
        raise ValueError("At least one object sequence is required.")
    ys, xs, plane_hits, ray_coefficients = prepare_camera_ray_geometry(metadata, mask)
    if ys.size == 0:
        raise ValueError("No valid object pixels available for depth solving.")

    observations = [np.moveaxis(sequence[:, ys, xs], 0, -1) for sequence in object_sequences]
    reference_model: list[tuple[np.ndarray, np.ndarray]] | None = None
    if reference_sequences is not None and reference_projector_x is not None:
        reference_x = reference_projector_x[ys, xs]
        reference_model = []
        for reference_sequence, phase_steps, period_px in zip(
            reference_sequences, phase_steps_rad, fringe_periods_px
        ):
            observed = np.moveaxis(reference_sequence[:, ys, xs], 0, -1)
            basis = np.sin((2.0 * math.pi / period_px) * reference_x[:, None] + phase_steps[None, :])
            offsets = np.mean(observed, axis=1)
            centered = observed - offsets[:, None]
            denominator = np.sum(basis * basis, axis=1)
            gains = np.divide(
                np.sum(centered * basis, axis=1),
                denominator,
                out=np.full_like(offsets, 0.5),
                where=denominator > 1e-12,
            )
            reference_model.append((offsets, gains))

    coarse_depths = np.arange(0.0, max_depth_m + (coarse_step_m * 0.5), coarse_step_m, dtype=np.float64)
    fine_offsets = np.arange(
        -fine_half_window_m,
        fine_half_window_m + (fine_step_m * 0.5),
        fine_step_m,
        dtype=np.float64,
    )
    reconstructed = np.full(mask.shape, np.nan, dtype=np.float64)

    def loss(
        projector_x: np.ndarray,
        observation_groups: list[np.ndarray],
        start: int,
        end: int,
    ) -> np.ndarray:
        total = np.zeros(projector_x.shape, dtype=np.float64)
        for index, (observed, phase_steps, period_px) in enumerate(
            zip(observation_groups, phase_steps_rad, fringe_periods_px)
        ):
            basis = np.sin((2.0 * math.pi / period_px) * projector_x[..., None] + phase_steps)
            if reference_model is None:
                predicted = 0.5 + 0.5 * basis
            else:
                offsets, gains = reference_model[index]
                predicted = offsets[start:end, None, None] + gains[start:end, None, None] * basis
            total += np.mean((predicted - observed[:, None, :]) ** 2, axis=2)
        return total

    for start in range(0, ys.size, chunk_size):
        end = min(ys.size, start + chunk_size)
        plane_chunk = plane_hits[start:end]
        coefficient_chunk = ray_coefficients[start:end]
        observation_chunk = [observed[start:end] for observed in observations]

        coarse_points = plane_chunk[:, None, :] + coefficient_chunk[:, None, :] * coarse_depths[None, :, None]
        coarse_projector_x = projector_x_from_world_points(coarse_points, metadata)
        coarse_error = loss(coarse_projector_x, observation_chunk, start, end)
        candidate_count = min(coarse_candidate_count, coarse_error.shape[1])
        candidate_indices = np.argpartition(coarse_error, kth=candidate_count - 1, axis=1)[:, :candidate_count]
        candidate_depths = coarse_depths[candidate_indices]

        fine_depths = np.clip(
            candidate_depths[:, :, None] + fine_offsets[None, None, :],
            0.0,
            max_depth_m,
        ).reshape(end - start, -1)
        fine_points = plane_chunk[:, None, :] + coefficient_chunk[:, None, :] * fine_depths[..., None]
        fine_projector_x = projector_x_from_world_points(fine_points, metadata)
        fine_error = loss(fine_projector_x, observation_chunk, start, end)
        fine_indices = np.argmin(fine_error, axis=1)
        best_depth = fine_depths[np.arange(end - start), fine_indices]
        if quadratic_subsample:
            rows = np.arange(end - start)
            columns = fine_error.shape[1]
            best_error = fine_error[rows, fine_indices]
            interior = (fine_indices > 0) & (fine_indices < columns - 1)
            left = fine_error[rows, np.clip(fine_indices - 1, 0, columns - 1)]
            right = fine_error[rows, np.clip(fine_indices + 1, 0, columns - 1)]
            denominator = left - (2.0 * best_error) + right
            refine = interior & (np.abs(denominator) > 1e-12)
            offset = np.zeros(end - start, dtype=np.float64)
            offset[refine] = np.clip(0.5 * (left[refine] - right[refine]) / denominator[refine], -1.0, 1.0)
            best_depth = np.where(
                refine,
                np.clip(best_depth + offset * fine_step_m, 0.0, max_depth_m),
                best_depth,
            )
        reconstructed[ys[start:end], xs[start:end]] = best_depth

    return reconstructed, {
        "solver_pixels": int(ys.size),
        "coarse_depth_samples": int(coarse_depths.size),
        "fine_depth_samples": int(fine_offsets.size),
        "max_depth_m": float(max_depth_m),
        "coarse_candidate_count": int(coarse_candidate_count),
        "quadratic_subsample": int(quadratic_subsample),
    }
