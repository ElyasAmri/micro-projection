from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtGui import QImage

from ..core.constants import SURFACE_CAMERA_CAPTURE_HEIGHT_PX, SURFACE_CAMERA_CAPTURE_WIDTH_PX
from ..core.fringe import generate_fringe_image
from ..core.math3d import vec_dot, vec_subtract
from ..core.types import Vec3
from .reconstruction import (
    SimilarityMetrics,
    apply_height_calibration,
    fit_height_calibration,
    phase_shift_sequence,
    robust_modulation_mask,
    similarity_metrics,
    unwrap_phase_2d,
    wrapped_phase_delta,
)

if TYPE_CHECKING:
    from ..ui.window import ProjectionWindow


@dataclass(frozen=True)
class ReconstructionFrame:
    height: np.ndarray
    mask: np.ndarray
    metrics: SimilarityMetrics
    phase_delta: np.ndarray
    label: str


@dataclass(frozen=True)
class ScanReconstruction:
    height: np.ndarray
    truth: np.ndarray
    mask: np.ndarray
    metrics: SimilarityMetrics
    phase_delta: np.ndarray
    object_name: str
    frames: tuple[ReconstructionFrame, ...] = field(default_factory=tuple)


def capture_phase_sequence(
    window: ProjectionWindow,
    *,
    width: int,
    height: int,
    steps: int,
) -> np.ndarray:
    if steps < 3:
        raise ValueError("At least three phase steps are required.")

    previous_processed = window._processed
    frames: list[np.ndarray] = []
    try:
        for index in range(steps):
            phase_deg = 360.0 * index / steps
            fringe = generate_fringe_image(
                window.fringe_width,
                window.fringe_height,
                period_px=window.fringe_period_px,
                phase_deg=phase_deg,
                orientation=window.fringe_orientation,
                contrast=window.fringe_contrast,
                bias=window.fringe_bias,
            )
            window._processed = window._process_image(fringe)
            capture = window.render_surface_camera_telecentric_capture(width, height)
            frames.append(_qimage_to_luma(capture))
    finally:
        window._processed = previous_processed
    return np.stack(frames, axis=0)


def reconstruct_current_object(
    window: ProjectionWindow,
    *,
    width: int = SURFACE_CAMERA_CAPTURE_WIDTH_PX,
    height: int = SURFACE_CAMERA_CAPTURE_HEIGHT_PX,
    steps: int = 8,
) -> ScanReconstruction:
    original_project_field_object = window.project_field_object
    try:
        window.project_field_object = False
        reference_frames = capture_phase_sequence(
            window,
            width=width,
            height=height,
            steps=steps,
        )
        reference = phase_shift_sequence(reference_frames)

        window.project_field_object = original_project_field_object
        object_frames = capture_phase_sequence(
            window,
            width=width,
            height=height,
            steps=steps,
        )
    finally:
        window.project_field_object = original_project_field_object

    return reconstruct_from_phase_sequences(
        window,
        reference_frames,
        object_frames,
        width=width,
        height=height,
    )


def reconstruct_from_phase_sequences(
    window: ProjectionWindow,
    reference_frames: np.ndarray,
    object_frames: np.ndarray,
    *,
    width: int,
    height: int,
) -> ScanReconstruction:
    truth, truth_mask = ground_truth_height(window, width=width, height=height)
    frame_count = min(reference_frames.shape[0], object_frames.shape[0])
    frames: list[ReconstructionFrame] = []
    for count in range(3, frame_count + 1):
        frame = _reconstruct_frame(
            reference_frames[:count],
            object_frames[:count],
            truth,
            truth_mask,
            label=f"{count}/{frame_count} phase frames",
        )
        frames.append(frame)
    if not frames:
        raise ValueError("Scan did not produce enough valid samples to reconstruct.")
    final_frame = frames[-1]
    return ScanReconstruction(
        height=final_frame.height,
        truth=truth,
        mask=final_frame.mask,
        metrics=final_frame.metrics,
        phase_delta=final_frame.phase_delta,
        object_name=getattr(window, "field_object_kind", "box"),
        frames=tuple(frames),
    )


def _reconstruct_frame(
    reference_frames: np.ndarray,
    object_frames: np.ndarray,
    truth: np.ndarray,
    truth_mask: np.ndarray,
    *,
    label: str,
) -> ReconstructionFrame:
    reference = phase_shift_sequence(reference_frames)
    measured = phase_shift_sequence(object_frames)
    phase_delta = unwrap_phase_2d(
        wrapped_phase_delta(measured.wrapped_phase, reference.wrapped_phase)
    )
    modulation_mask = robust_modulation_mask(measured.modulation, reference.modulation)
    valid_mask = truth_mask & modulation_mask & np.isfinite(phase_delta)
    if np.count_nonzero(valid_mask) < 2:
        raise ValueError("Scan did not produce enough valid samples to reconstruct.")

    calibration_mask, evaluation_mask = _calibration_evaluation_masks(valid_mask)
    calibration = fit_height_calibration(
        phase_delta,
        truth,
        calibration_mask,
        include_spatial_terms=True,
    )
    height_map = apply_height_calibration(phase_delta, calibration)
    metrics = similarity_metrics(height_map, truth, evaluation_mask)
    return ReconstructionFrame(
        height=height_map,
        mask=valid_mask,
        metrics=metrics,
        phase_delta=phase_delta,
        label=label,
    )


def _calibration_evaluation_masks(valid_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rows, columns = np.indices(valid_mask.shape)
    calibration_mask = valid_mask & ((rows + columns) % 2 == 0)
    evaluation_mask = valid_mask & ~calibration_mask
    if np.count_nonzero(calibration_mask) < 2 or np.count_nonzero(evaluation_mask) < 1:
        return valid_mask, valid_mask
    return calibration_mask, evaluation_mask


def nuanced_field_object_faces(
    window: ProjectionWindow,
    *,
    columns: int = 16,
    rows: int = 10,
) -> list[list[Vec3]]:
    frame = window._field_object_frame()
    if frame is None:
        return []
    plane_center, right, up, normal = frame
    width = 9.0
    height = 7.0

    def point(u: float, v: float) -> Vec3:
        x_norm = u / (width * 0.5)
        y_norm = v / (height * 0.5)
        dome = 1.15 * np.exp(-1.8 * (x_norm * x_norm + y_norm * y_norm))
        ripple = 0.22 * np.sin(3.0 * np.pi * x_norm) * np.cos(2.0 * np.pi * y_norm)
        ridge = 0.28 * np.exp(-24.0 * (y_norm + 0.25) ** 2)
        depth = 0.25 + max(0.0, float(dome + ripple + ridge))
        return (
            plane_center[0] + right[0] * u + up[0] * v + normal[0] * depth,
            plane_center[1] + right[1] * u + up[1] * v + normal[1] * depth,
            plane_center[2] + right[2] * u + up[2] * v + normal[2] * depth,
        )

    faces: list[list[Vec3]] = []
    for row in range(rows):
        v0 = -height * 0.5 + height * row / rows
        v1 = -height * 0.5 + height * (row + 1) / rows
        for column in range(columns):
            u0 = -width * 0.5 + width * column / columns
            u1 = -width * 0.5 + width * (column + 1) / columns
            faces.append([point(u0, v1), point(u1, v1), point(u1, v0), point(u0, v0)])
    return faces


def ground_truth_height(
    window: ProjectionWindow,
    *,
    width: int,
    height: int,
) -> tuple[np.ndarray, np.ndarray]:
    scan_context = window._surface_camera_telecentric_scan_context(width, height)
    if scan_context is None:
        raise RuntimeError("Surface camera scan context is unavailable.")
    surfaces = window._scene_surfaces()
    plane_center, normal = _plane_height_frame(window)

    truth = np.full((height, width), np.nan, dtype=np.float64)
    mask = np.zeros((height, width), dtype=bool)
    for y in range(height):
        for x in range(width):
            hit = window._first_telecentric_scan_hit(
                x + 0.5,
                y + 0.5,
                width,
                height,
                scan_context,
                surfaces,
            )
            if hit is None:
                continue
            world = hit[1]
            truth[y, x] = vec_dot(vec_subtract(world, plane_center), normal)
            mask[y, x] = True
    return truth, mask


def _plane_height_frame(window: ProjectionWindow) -> tuple[Vec3, Vec3]:
    frame = window._field_object_frame()
    if frame is not None:
        plane_center, _, _, normal = frame
        return plane_center, normal
    return window._plane_center(), (0.0, -1.0, 0.0)


def _qimage_to_luma(image: QImage) -> np.ndarray:
    rgb = image.convertToFormat(QImage.Format_RGB888)
    width = rgb.width()
    height = rgb.height()
    row_stride = rgb.bytesPerLine()
    buffer = np.frombuffer(rgb.bits(), dtype=np.uint8).reshape((height, row_stride))
    pixels = buffer[:, : width * 3].reshape((height, width, 3))
    return pixels.astype(np.float64).mean(axis=2) / 255.0
