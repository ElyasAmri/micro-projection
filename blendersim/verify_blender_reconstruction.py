from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import cv2
import imageio.v2 as imageio
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from projection_simulation.scanning.reconstruction import (
    SimilarityMetrics,
    normalize_to_uint8,
    phase_shift_sequence,
    robust_modulation_mask,
    similarity_metrics,
)
from shared.synthetic_surfaces import SURFACE_KINDS, height_field_depth_m

DEFAULT_PHASE_DEG = [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0]
MEASUREMENT_FIDELITY_PHASE_DEG = [float(index) * 22.5 for index in range(16)]
IMPROVEMENT_ORDER: tuple[str, ...] = (
    "truth-render-alignment",
    "absolute-correspondence",
    "solver-refinement",
    "reference-normalization",
    "measurement-fidelity",
    "verifier-cleanup",
)
OPTIMIZED_IMPROVEMENTS: tuple[str, ...] = (
    "absolute-correspondence",
    "solver-refinement",
    "measurement-fidelity",
    "verifier-cleanup",
)


@dataclass(frozen=True)
class ImprovementSettings:
    fringe_periods_px: list[float]
    phase_deg: list[float]
    mesh_columns: int
    mesh_rows: int
    cycles_samples: int
    solver_candidate_count: int
    quadratic_subsample: bool
    use_reference_normalization: bool
    cleanup_only: bool


@dataclass(frozen=True)
class ReconstructionSnapshot:
    solved_count: int
    total_count: int
    reconstructed: np.ndarray


@dataclass(frozen=True)
class CaptureReconstructionStage:
    capture_index: int
    total_captures: int
    period_index: int
    period_count: int
    period_px: float
    phase_deg: float
    capture_frame: np.ndarray
    reconstructed: np.ndarray
    solved_mask: np.ndarray
    metrics: SimilarityMetrics | None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify phase-shift reconstruction on the Blender synthetic scene.")
    parser.add_argument(
        "--blender-exe",
        default=r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
        help="Path to blender.exe.",
    )
    parser.add_argument(
        "--scene-script",
        default=str(Path(__file__).with_name("blender_projector_capture.py")),
        help="Path to the Blender scene generation script.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parents[1] / "out" / "blender_reconstruction_verify"),
        help="Directory for Blender renders and verification outputs.",
    )
    parser.add_argument("--render-width", type=int, default=1028)
    parser.add_argument("--render-height", type=int, default=752)
    parser.add_argument(
        "--surface-kind",
        default="dome-ridge",
        choices=SURFACE_KINDS,
        help="Synthetic surface profile to render in Blender.",
    )
    parser.add_argument(
        "--fringe-periods-px",
        type=float,
        nargs="+",
        default=[48.0, 192.0],
        help="Projector fringe periods to render and jointly solve.",
    )
    parser.add_argument(
        "--phase-deg",
        type=float,
        nargs="+",
        default=None,
    )
    parser.add_argument("--mesh-columns", type=int, default=160)
    parser.add_argument("--mesh-rows", type=int, default=120)
    parser.add_argument("--cycles-samples", type=int, default=8)
    parser.add_argument(
        "--enabled-improvements",
        nargs="*",
        default=[],
        choices=IMPROVEMENT_ORDER,
        help="Enable experimental reconstruction improvements for ablation benchmarks.",
    )
    parser.add_argument(
        "--optimized",
        action="store_true",
        help="Enable the non-regressing optimized reconstruction preset.",
    )
    parser.add_argument(
        "--skip-thresholds",
        action="store_true",
        help="Do not fail the process when benchmark metrics miss the default thresholds.",
    )
    parser.add_argument(
        "--record-reconstruction-video",
        default=None,
        help="Optional MP4 path for a progress recording of the reconstruction solve.",
    )
    parser.add_argument(
        "--record-fps",
        type=float,
        default=12.0,
        help="FPS for the optional reconstruction progress recording.",
    )
    parser.add_argument(
        "--record-snapshot-frames",
        type=int,
        default=24,
        help="Legacy option retained for compatibility; per-capture recordings now use every capture.",
    )
    return parser.parse_args()


def _resolve_improvement_settings(args: argparse.Namespace) -> ImprovementSettings:
    enabled = set(args.enabled_improvements)
    if args.optimized:
        enabled.update(OPTIMIZED_IMPROVEMENTS)
    fringe_periods = [float(period) for period in args.fringe_periods_px]
    if "absolute-correspondence" in enabled and 768.0 not in fringe_periods:
        fringe_periods.append(768.0)

    phase_deg = list(args.phase_deg) if args.phase_deg is not None else list(DEFAULT_PHASE_DEG)
    cycles_samples = int(args.cycles_samples)
    if "measurement-fidelity" in enabled:
        if args.phase_deg is None:
            phase_deg = list(MEASUREMENT_FIDELITY_PHASE_DEG)
        cycles_samples = max(cycles_samples, 32)

    mesh_columns = int(args.mesh_columns)
    mesh_rows = int(args.mesh_rows)
    if "truth-render-alignment" in enabled:
        mesh_columns = max(mesh_columns, 480)
        mesh_rows = max(mesh_rows, 360)

    solver_candidate_count = 3 if "solver-refinement" in enabled else 1
    quadratic_subsample = "solver-refinement" in enabled
    use_reference_normalization = "reference-normalization" in enabled
    cleanup_only = enabled == {"verifier-cleanup"}
    return ImprovementSettings(
        fringe_periods_px=fringe_periods,
        phase_deg=phase_deg,
        mesh_columns=mesh_columns,
        mesh_rows=mesh_rows,
        cycles_samples=cycles_samples,
        solver_candidate_count=solver_candidate_count,
        quadratic_subsample=quadratic_subsample,
        use_reference_normalization=use_reference_normalization,
        cleanup_only=cleanup_only,
    )


def _load_sequence(directory: Path, prefix: str) -> np.ndarray:
    frames: list[np.ndarray] = []
    for path in sorted(directory.glob(f"{prefix}_phase_*.png")):
        image = imageio.imread(path)
        if image.ndim == 3:
            image = image[..., :3].mean(axis=2)
        data = np.asarray(image)
        if np.issubdtype(data.dtype, np.integer):
            scale = float(np.iinfo(data.dtype).max)
            frames.append(data.astype(np.float64) / scale)
        else:
            frames.append(data.astype(np.float64))
    if len(frames) < 3:
        raise ValueError(f"Expected at least three {prefix} frames in {directory}.")
    return np.stack(frames, axis=0)


def _calibration_evaluation_masks(valid_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rows, columns = np.indices(valid_mask.shape)
    calibration_mask = valid_mask & ((rows + columns) % 2 == 0)
    evaluation_mask = valid_mask & ~calibration_mask
    if np.count_nonzero(calibration_mask) < 2 or np.count_nonzero(evaluation_mask) < 1:
        return valid_mask, valid_mask
    return calibration_mask, evaluation_mask


def _write_uint8(path: Path, values: np.ndarray, mask: np.ndarray | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    imageio.imwrite(path, normalize_to_uint8(values, mask))


def _colorize_scalar_map(
    values: np.ndarray,
    mask: np.ndarray,
    *,
    lo: float,
    hi: float,
    invalid_rgb: tuple[int, int, int] = (10, 12, 16),
    colormap: int = cv2.COLORMAP_TURBO,
) -> np.ndarray:
    valid = mask & np.isfinite(values)
    rgb = np.zeros((*values.shape, 3), dtype=np.uint8)
    rgb[...] = np.asarray(invalid_rgb, dtype=np.uint8)
    if not np.any(valid):
        return rgb
    if hi <= lo:
        scaled = np.full(values.shape, 127, dtype=np.uint8)
    else:
        normalized = np.clip((values - lo) / (hi - lo), 0.0, 1.0)
        scaled = np.round(normalized * 255.0).astype(np.uint8)
    colored = cv2.applyColorMap(scaled, colormap)
    colored = cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)
    rgb[valid] = colored[valid]
    return rgb


def _draw_panel(
    canvas: np.ndarray,
    image: np.ndarray,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    title: str,
    subtitle: str | None = None,
) -> None:
    panel = cv2.resize(image, (width, height), interpolation=cv2.INTER_NEAREST)
    canvas[y : y + height, x : x + width] = panel
    cv2.rectangle(canvas, (x, y - 34), (x + width, y), (22, 26, 34), thickness=-1)
    cv2.putText(canvas, title, (x + 8, y - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (236, 240, 246), 1, cv2.LINE_AA)
    if subtitle:
        cv2.putText(canvas, subtitle, (x + 8, y + height + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (175, 186, 202), 1, cv2.LINE_AA)


def _capture_frame_rgb(frame: np.ndarray) -> np.ndarray:
    normalized = np.clip(np.asarray(frame, dtype=np.float64), 0.0, 1.0)
    grayscale = np.round(normalized * 255.0).astype(np.uint8)
    return np.repeat(grayscale[..., None], 3, axis=2)


def _build_capture_reconstruction_stages(
    metadata: dict[str, object],
    *,
    truth: np.ndarray,
    valid_mask: np.ndarray,
    object_mask: np.ndarray,
    reference_frames_list: list[np.ndarray],
    object_frames_list: list[np.ndarray],
    phase_deg: list[float],
    fringe_periods_px: list[float],
    use_reference_normalization: bool,
    reference_projector_x: np.ndarray,
    coarse_candidate_count: int,
    quadratic_subsample: bool,
) -> list[CaptureReconstructionStage]:
    phase_steps_full = np.deg2rad(np.asarray(phase_deg, dtype=np.float64))
    capture_counts = [0] * len(object_frames_list)
    total_captures = int(sum(sequence.shape[0] for sequence in object_frames_list))
    stages: list[CaptureReconstructionStage] = []
    capture_index = 0

    for period_index, object_sequence in enumerate(object_frames_list):
        for phase_index in range(object_sequence.shape[0]):
            capture_index += 1
            capture_counts[period_index] += 1
            available_period_indices = [index for index, count in enumerate(capture_counts) if count >= 3]

            reconstructed = np.full(valid_mask.shape, np.nan, dtype=np.float64)
            solved_mask = np.zeros(valid_mask.shape, dtype=bool)
            stage_metrics: SimilarityMetrics | None = None

            if available_period_indices:
                stage_reference_frames = [reference_frames_list[index][: capture_counts[index]] for index in available_period_indices]
                stage_object_frames = [object_frames_list[index][: capture_counts[index]] for index in available_period_indices]
                stage_reference_sequences = [phase_shift_sequence(frames) for frames in stage_reference_frames]
                stage_object_sequences = [phase_shift_sequence(frames) for frames in stage_object_frames]
                stage_modulation_mask = robust_modulation_mask(
                    *[sequence.modulation for sequence in stage_object_sequences],
                    *[sequence.modulation for sequence in stage_reference_sequences],
                )
                stage_valid_object_mask = object_mask & valid_mask & stage_modulation_mask
                if np.count_nonzero(stage_valid_object_mask) >= 20:
                    reconstructed, _ = _direct_photometric_depth_solve(
                        metadata,
                        stage_valid_object_mask,
                        stage_object_frames,
                        [phase_steps_full[: capture_counts[index]] for index in available_period_indices],
                        [fringe_periods_px[index] for index in available_period_indices],
                        reference_sequences=stage_reference_frames if use_reference_normalization else None,
                        reference_projector_x=reference_projector_x if use_reference_normalization else None,
                        coarse_candidate_count=coarse_candidate_count,
                        quadratic_subsample=quadratic_subsample,
                    )
                    solved_mask = stage_valid_object_mask & np.isfinite(reconstructed)
                    if np.count_nonzero(solved_mask) >= 20:
                        stage_metrics = similarity_metrics(reconstructed, truth, solved_mask)

            stages.append(
                CaptureReconstructionStage(
                    capture_index=capture_index,
                    total_captures=total_captures,
                    period_index=period_index,
                    period_count=capture_counts[period_index],
                    period_px=float(fringe_periods_px[period_index]),
                    phase_deg=float(phase_deg[phase_index]),
                    capture_frame=object_sequence[phase_index],
                    reconstructed=reconstructed,
                    solved_mask=solved_mask,
                    metrics=stage_metrics,
                )
            )
    return stages


def _write_reconstruction_recording(
    output_path: Path,
    *,
    surface_kind: str,
    stages: list[CaptureReconstructionStage],
    truth: np.ndarray,
    final_mask: np.ndarray,
    metrics,
    fps: float,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    valid_truth = final_mask & np.isfinite(truth)
    if not np.any(valid_truth):
        raise ValueError("Cannot record reconstruction without valid truth samples.")

    truth_lo = float(np.percentile(truth[valid_truth], 2.0))
    truth_hi = float(np.percentile(truth[valid_truth], 98.0))
    final_abs_error = np.abs(stages[-1].reconstructed - truth) * 100.0
    valid_error = np.isfinite(final_abs_error) & final_mask
    error_hi = float(np.percentile(final_abs_error[valid_error], 98.0)) if np.any(valid_error) else 0.1
    error_hi = max(0.01, error_hi)

    truth_panel = _colorize_scalar_map(truth, final_mask, lo=truth_lo, hi=truth_hi)
    writer = imageio.get_writer(str(output_path), fps=fps, macro_block_size=None)
    try:
        for hold_index, stage in enumerate([stages[0], *stages, stages[-1], stages[-1]]):
            current_mask = np.isfinite(stage.reconstructed) & final_mask
            current_error = np.full_like(truth, np.nan, dtype=np.float64)
            current_error[current_mask] = np.abs(stage.reconstructed[current_mask] - truth[current_mask]) * 100.0
            capture_panel = _capture_frame_rgb(stage.capture_frame)
            reconstruction_panel = _colorize_scalar_map(
                stage.reconstructed,
                current_mask,
                lo=truth_lo,
                hi=truth_hi,
            )
            error_panel = _colorize_scalar_map(
                current_error,
                current_mask,
                lo=0.0,
                hi=error_hi,
                invalid_rgb=(14, 14, 18),
                colormap=cv2.COLORMAP_MAGMA,
            )

            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            frame[...] = np.asarray((8, 10, 14), dtype=np.uint8)
            cv2.putText(
                frame,
                f"Reconstruction process - {surface_kind.replace('-', ' ')}",
                (36, 42),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.95,
                (236, 240, 246),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                frame,
                (
                    f"Capture {stage.capture_index:02d}/{stage.total_captures:02d}"
                    f"  |  Period {stage.period_px:.0f}px capture {stage.period_count:02d}"
                    f"  |  Phase {stage.phase_deg:.1f} deg"
                ),
                (36, 78),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (184, 194, 208),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                frame,
                (
                    f"Current metrics: "
                    + (
                        f"R2={stage.metrics.r2:.4f}  RMSE={stage.metrics.rmse * 100.0:.4f} cm"
                        if stage.metrics is not None
                        else "insufficient captures for reconstruction"
                    )
                ),
                (36, 110),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (184, 194, 208),
                1,
                cv2.LINE_AA,
            )

            panel_y = 160
            panel_w = 380
            panel_h = 380
            _draw_panel(
                frame,
                capture_panel,
                x=36,
                y=panel_y,
                width=panel_w,
                height=panel_h,
                title="Current capture",
                subtitle="Captured object fringe image",
            )
            _draw_panel(
                frame,
                reconstruction_panel,
                x=450,
                y=panel_y,
                width=panel_w,
                height=panel_h,
                title="Current reconstruction",
                subtitle="Reconstruction using captures so far",
            )
            _draw_panel(
                frame,
                truth_panel,
                x=864,
                y=panel_y,
                width=panel_w,
                height=panel_h,
                title="Ground truth",
                subtitle="Reference height map",
            )

            bar_x = 36
            bar_y = 620
            bar_w = 1208
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + 24), (24, 28, 36), thickness=-1)
            progress = stage.capture_index / max(1, stage.total_captures)
            cv2.rectangle(
                frame,
                (bar_x, bar_y),
                (bar_x + int(round(bar_w * progress)), bar_y + 24),
                (70, 160, 250),
                thickness=-1,
            )
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + 24), (58, 66, 82), thickness=1)
            cv2.putText(
                frame,
                f"Final result benchmark: R2={metrics.r2:.4f}  RMSE={metrics.rmse * 100.0:.4f} cm",
                (36, 680),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (170, 180, 196),
                1,
                cv2.LINE_AA,
            )

            repeat = 1
            if hold_index == 0:
                repeat = max(2, int(round(fps * 0.75)))
            elif hold_index >= len(stages):
                repeat = max(2, int(round(fps * 0.75)))
            for _ in range(repeat):
                writer.append_data(frame)
    finally:
        writer.close()


def _period_label(period_px: float) -> str:
    return str(period_px).replace(".", "p")


def _normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        raise ValueError("Cannot normalize zero-length vector.")
    return vector / norm


def _matrix_from_rows(rows: object) -> np.ndarray:
    matrix = np.asarray(rows, dtype=np.float64)
    if matrix.shape != (4, 4):
        raise ValueError("Expected a 4x4 transform matrix in metadata.")
    return matrix


def _frame_bounds_from_metadata(metadata: dict[str, object], key: str) -> tuple[float, float, float, float, float]:
    values = np.asarray(metadata[key], dtype=np.float64)
    if values.shape != (5,):
        raise ValueError(f"Expected five frame-bound values in metadata key '{key}'.")
    return (float(values[0]), float(values[1]), float(values[2]), float(values[3]), float(values[4]))


def _transform_point(matrix_world: np.ndarray, point: np.ndarray) -> np.ndarray:
    homogeneous = np.append(np.asarray(point, dtype=np.float64), 1.0)
    return (matrix_world @ homogeneous)[:3]


def _transform_direction(matrix_world: np.ndarray, direction: np.ndarray) -> np.ndarray:
    return matrix_world[:3, :3] @ np.asarray(direction, dtype=np.float64)


def _capture_ray_from_pixel(
    metadata: dict[str, object],
    x: int,
    y: int,
) -> tuple[np.ndarray, np.ndarray]:
    width = int(metadata["render_width"])
    height = int(metadata["render_height"])
    min_x, max_x, min_y, max_y, frame_z = _frame_bounds_from_metadata(
        metadata,
        "capture_camera_frame_bounds_local",
    )
    camera_matrix = _matrix_from_rows(metadata["capture_camera_matrix_world"])
    nx = (x + 0.5) / width
    ny = 1.0 - ((y + 0.5) / height)
    local_point = np.array(
        [
            min_x + (max_x - min_x) * nx,
            min_y + (max_y - min_y) * ny,
            0.0,
        ],
        dtype=np.float64,
    )
    origin = _transform_point(camera_matrix, local_point)
    direction = _normalize(_transform_direction(camera_matrix, np.array([0.0, 0.0, -1.0], dtype=np.float64)))
    return origin, direction


def _plane_geometry(metadata: dict[str, object]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    plane_matrix = _matrix_from_rows(metadata["plane_matrix_world"])
    plane_center = _transform_point(plane_matrix, np.array([0.0, 0.0, 0.0], dtype=np.float64))
    plane_right = _normalize(_transform_direction(plane_matrix, np.array([1.0, 0.0, 0.0], dtype=np.float64)))
    plane_up = _normalize(_transform_direction(plane_matrix, np.array([0.0, 1.0, 0.0], dtype=np.float64)))
    plane_normal = _normalize(_transform_direction(plane_matrix, np.array([0.0, 0.0, 1.0], dtype=np.float64)))
    return plane_center, plane_right, plane_up, plane_normal


def _intersect_ray_with_plane(
    origin: np.ndarray,
    direction: np.ndarray,
    plane_point: np.ndarray,
    plane_normal: np.ndarray,
) -> np.ndarray | None:
    denominator = float(np.dot(direction, plane_normal))
    if abs(denominator) <= 1e-12:
        return None
    distance = float(np.dot(plane_point - origin, plane_normal) / denominator)
    if distance <= 1e-9:
        return None
    return origin + direction * distance


def _project_world_to_projector_x(world_point: np.ndarray, metadata: dict[str, object]) -> float:
    projector_matrix = _matrix_from_rows(metadata["projector_matrix_world"])
    projector_world_to_local = np.linalg.inv(projector_matrix)
    local_point = _transform_point(projector_world_to_local, world_point)
    min_x, max_x, _, _, frame_z = _frame_bounds_from_metadata(metadata, "projector_frame_bounds_local")
    if abs(float(local_point[2])) <= 1e-12:
        raise ValueError("World point lies on the projector origin plane.")
    projected_frame_x = float(local_point[0] * (frame_z / local_point[2]))
    normalized = (projected_frame_x - min_x) / (max_x - min_x)
    return normalized * int(metadata["fringe_width"]) - 0.5


def _projector_x_from_world_points(points: np.ndarray, metadata: dict[str, object]) -> np.ndarray:
    projector_matrix = _matrix_from_rows(metadata["projector_matrix_world"])
    projector_world_to_local = np.linalg.inv(projector_matrix)
    min_x, max_x, _, _, frame_z = _frame_bounds_from_metadata(metadata, "projector_frame_bounds_local")
    fringe_width = float(metadata["fringe_width"])
    homogeneous = np.concatenate(
        [np.asarray(points, dtype=np.float64), np.ones((*points.shape[:-1], 1), dtype=np.float64)],
        axis=-1,
    )
    local = homogeneous @ projector_world_to_local.T
    frame_x = local[..., 0] * (frame_z / local[..., 2])
    normalized = (frame_x - min_x) / (max_x - min_x)
    return normalized * fringe_width - 0.5


def _projector_column_plane(
    metadata: dict[str, object],
    projector_x: float,
) -> tuple[np.ndarray, np.ndarray]:
    projector_matrix = _matrix_from_rows(metadata["projector_matrix_world"])
    projector_center = _transform_point(projector_matrix, np.array([0.0, 0.0, 0.0], dtype=np.float64))
    min_x, max_x, min_y, max_y, frame_z = _frame_bounds_from_metadata(metadata, "projector_frame_bounds_local")
    projector_width = int(metadata["fringe_width"])
    normalized = (projector_x + 0.5) / projector_width
    local_x = min_x + (max_x - min_x) * normalized
    bottom_point = _transform_point(projector_matrix, np.array([local_x, min_y, frame_z], dtype=np.float64))
    top_point = _transform_point(projector_matrix, np.array([local_x, max_y, frame_z], dtype=np.float64))
    plane_normal = _normalize(np.cross(bottom_point - projector_center, top_point - projector_center))
    return projector_center, plane_normal


def _height_field_intersection(
    origin: np.ndarray,
    direction: np.ndarray,
    plane_center: np.ndarray,
    plane_right: np.ndarray,
    plane_up: np.ndarray,
    plane_normal: np.ndarray,
    patch_width: float,
    patch_height: float,
    surface_kind: str,
) -> tuple[np.ndarray, float, bool] | None:
    denominator = float(np.dot(direction, plane_normal))
    if abs(denominator) <= 1e-12:
        return None
    plane_t = float(np.dot(plane_center - origin, plane_normal) / denominator)
    if plane_t <= 1e-9:
        return None

    def signed_height_error(distance: float) -> tuple[float, float]:
        point = origin + direction * distance
        offset = point - plane_center
        u = float(np.dot(offset, plane_right))
        v = float(np.dot(offset, plane_up))
        if abs(u) <= patch_width * 0.5 and abs(v) <= patch_height * 0.5:
            depth = height_field_depth_m(u, v, patch_width, patch_height, surface_kind=surface_kind)
        else:
            depth = 0.0
        height = float(np.dot(offset, plane_normal))
        return height - depth, depth

    t_hi = plane_t
    f_hi, depth_hi = signed_height_error(t_hi)
    max_depth_m = 0.03
    t_lo = max(0.0, plane_t - ((max_depth_m + 0.002) / abs(denominator)))
    f_lo, _ = signed_height_error(t_lo)
    expand_count = 0
    while f_lo <= 0.0 and t_lo > 0.0 and expand_count < 8:
        t_lo = max(0.0, t_lo - ((max_depth_m + 0.002) / abs(denominator)))
        f_lo, _ = signed_height_error(t_lo)
        expand_count += 1
    if f_hi > 0.0:
        return None
    if depth_hi <= 1e-9:
        return origin + direction * plane_t, 0.0, False
    if f_lo <= 0.0:
        return None

    for _ in range(48):
        t_mid = 0.5 * (t_lo + t_hi)
        f_mid, _ = signed_height_error(t_mid)
        if f_mid > 0.0:
            t_lo = t_mid
        else:
            t_hi = t_mid
    point = origin + direction * t_hi
    offset = point - plane_center
    u = float(np.dot(offset, plane_right))
    v = float(np.dot(offset, plane_up))
    depth = height_field_depth_m(u, v, patch_width, patch_height, surface_kind=surface_kind)
    return point, depth, True


def _load_ground_truth(output_dir: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    truth_data = np.load(output_dir / "ground_truth.npz")
    return (
        np.asarray(truth_data["truth"], dtype=np.float64),
        np.asarray(truth_data["valid_mask"], dtype=bool),
        np.asarray(truth_data["object_mask"], dtype=bool),
    )


def _reference_projector_x_map(
    metadata: dict[str, object],
    valid_mask: np.ndarray,
) -> np.ndarray:
    plane_center, _, _, plane_normal = _plane_geometry(metadata)
    projector_x = np.full(valid_mask.shape, np.nan, dtype=np.float64)
    for y, x in np.argwhere(valid_mask):
        ray_origin, ray_direction = _capture_ray_from_pixel(metadata, int(x), int(y))
        plane_hit = _intersect_ray_with_plane(ray_origin, ray_direction, plane_center, plane_normal)
        if plane_hit is None:
            continue
        projector_x[y, x] = _project_world_to_projector_x(plane_hit, metadata)
    return projector_x


def _prepare_camera_ray_geometry(
    metadata: dict[str, object],
    mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    plane_center, _, _, plane_normal = _plane_geometry(metadata)
    ys, xs = np.where(mask)
    plane_hits = np.empty((len(xs), 3), dtype=np.float64)
    ray_coefficients = np.empty((len(xs), 3), dtype=np.float64)
    for index, (y, x) in enumerate(zip(ys, xs)):
        origin, direction = _capture_ray_from_pixel(metadata, int(x), int(y))
        denominator = float(np.dot(direction, plane_normal))
        plane_t = float(np.dot(plane_center - origin, plane_normal) / denominator)
        plane_hits[index] = origin + direction * plane_t
        ray_coefficients[index] = direction / denominator
    return ys, xs, plane_hits, ray_coefficients


def _direct_photometric_depth_solve(
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
    progress_callback: Callable[[np.ndarray, int, int], None] | None = None,
) -> tuple[np.ndarray, dict[str, float | int]]:
    if not object_sequences:
        raise ValueError("At least one object sequence is required.")
    ys, xs, plane_hits, ray_coefficients = _prepare_camera_ray_geometry(metadata, mask)
    if ys.size == 0:
        raise ValueError("No valid object pixels available for depth solving.")

    observations = [np.moveaxis(sequence[:, ys, xs], 0, -1) for sequence in object_sequences]
    reference_model: list[tuple[np.ndarray, np.ndarray]] | None = None
    if reference_sequences is not None and reference_projector_x is not None:
        reference_x = reference_projector_x[ys, xs]
        reference_model = []
        for reference_sequence, phase_steps, period_px in zip(reference_sequences, phase_steps_rad, fringe_periods_px):
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
    solved_depth = np.empty(ys.size, dtype=np.float64)
    reconstructed = np.full(mask.shape, np.nan, dtype=np.float64)
    if progress_callback is not None:
        progress_callback(reconstructed, 0, int(ys.size))

    def loss(
        projector_x: np.ndarray,
        observation_groups: list[np.ndarray],
        start: int,
        end: int,
    ) -> np.ndarray:
        total = np.zeros(projector_x.shape, dtype=np.float64)
        for index, (observed, phase_steps, period_px) in enumerate(zip(observation_groups, phase_steps_rad, fringe_periods_px)):
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
        coarse_projector_x = _projector_x_from_world_points(coarse_points, metadata)
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
        fine_projector_x = _projector_x_from_world_points(fine_points, metadata)
        fine_error = loss(fine_projector_x, observation_chunk, start, end)
        fine_indices = np.argmin(fine_error, axis=1)
        best_depth = fine_depths[np.arange(end - start), fine_indices]
        if quadratic_subsample:
            refined_depth = best_depth.copy()
            best_error = fine_error[np.arange(end - start), fine_indices]
            for local_index, best_index in enumerate(fine_indices):
                if best_index <= 0 or best_index >= fine_error.shape[1] - 1:
                    continue
                left = fine_error[local_index, best_index - 1]
                center = best_error[local_index]
                right = fine_error[local_index, best_index + 1]
                denominator = left - (2.0 * center) + right
                if abs(float(denominator)) <= 1e-12:
                    continue
                offset = 0.5 * (left - right) / denominator
                refined_depth[local_index] = np.clip(
                    best_depth[local_index] + (float(np.clip(offset, -1.0, 1.0)) * fine_step_m),
                    0.0,
                    max_depth_m,
                )
            best_depth = refined_depth
        solved_depth[start:end] = best_depth
        reconstructed[ys[start:end], xs[start:end]] = best_depth
        if progress_callback is not None:
            progress_callback(reconstructed, int(end), int(ys.size))

    return reconstructed, {
        "solver_pixels": int(ys.size),
        "coarse_depth_samples": int(coarse_depths.size),
        "fine_depth_samples": int(fine_offsets.size),
        "max_depth_m": float(max_depth_m),
        "coarse_candidate_count": int(coarse_candidate_count),
        "quadratic_subsample": int(quadratic_subsample),
    }


def main() -> int:
    args = _parse_args()
    settings = _resolve_improvement_settings(args)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    period_outputs: list[Path] = []
    for period_px in settings.fringe_periods_px:
        period_dir = output_dir / f"period_{_period_label(period_px)}"
        if period_dir.exists():
            shutil.rmtree(period_dir)
        period_dir.mkdir(parents=True, exist_ok=True)

        command = [
            str(Path(args.blender_exe)),
            "-b",
            "-P",
            str(Path(args.scene_script)),
            "--",
            "--output-dir",
            str(period_dir),
            "--render-width",
            str(args.render_width),
            "--render-height",
            str(args.render_height),
            "--surface-kind",
            str(args.surface_kind),
            "--mesh-columns",
            str(settings.mesh_columns),
            "--mesh-rows",
            str(settings.mesh_rows),
            "--cycles-samples",
            str(settings.cycles_samples),
            "--fringe-period-px",
            str(period_px),
            "--phase-deg",
            *[str(phase) for phase in settings.phase_deg],
        ]
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            return completed.returncode
        period_outputs.append(period_dir)

    metadata = json.loads((period_outputs[0] / "metadata.json").read_text(encoding="utf-8"))
    truth, valid_mask, object_mask = _load_ground_truth(period_outputs[0])

    reference_frames_list = [_load_sequence(period_dir / "reference", "reference") for period_dir in period_outputs]
    object_frames_list = [_load_sequence(period_dir / "object", "object") for period_dir in period_outputs]
    reference_sequences = [phase_shift_sequence(frames) for frames in reference_frames_list]
    object_sequences = [phase_shift_sequence(frames) for frames in object_frames_list]
    modulation_mask = robust_modulation_mask(
        *[sequence.modulation for sequence in object_sequences],
        *[sequence.modulation for sequence in reference_sequences],
    )
    valid_object_mask = object_mask & valid_mask & modulation_mask
    if np.count_nonzero(valid_object_mask) < 20:
        raise ValueError("Not enough valid object samples for reconstruction verification.")

    reference_projector_x = _reference_projector_x_map(metadata, valid_mask)

    reconstructed, solver = _direct_photometric_depth_solve(
        metadata,
        valid_object_mask,
        object_frames_list,
        [np.deg2rad(np.asarray(settings.phase_deg, dtype=np.float64)) for _ in object_frames_list],
        [float(period) for period in settings.fringe_periods_px],
        reference_sequences=reference_frames_list if settings.use_reference_normalization else None,
        reference_projector_x=reference_projector_x if settings.use_reference_normalization else None,
        coarse_candidate_count=settings.solver_candidate_count,
        quadratic_subsample=settings.quadratic_subsample,
    )
    solved_mask = valid_object_mask & np.isfinite(reconstructed)
    if np.count_nonzero(solved_mask) < 20:
        raise ValueError("Direct depth solving did not produce enough valid object samples.")
    metrics = similarity_metrics(reconstructed, truth, solved_mask)

    error = reconstructed - truth
    _write_uint8(output_dir / "reconstruction_height.png", reconstructed, solved_mask)
    _write_uint8(output_dir / "truth_height.png", truth, solved_mask)
    _write_uint8(output_dir / "abs_error.png", np.abs(error), solved_mask)
    _write_uint8(output_dir / "depth_error_signed.png", error, solved_mask)
    imageio.imwrite(output_dir / "object_mask.png", (solved_mask.astype(np.uint8) * 255))

    result = {
        "capture_dir": str(output_dir),
        "surface_kind": str(args.surface_kind),
        "phase_count": int(object_frames_list[0].shape[0]),
        "fringe_periods_px": [float(period) for period in settings.fringe_periods_px],
        "enabled_improvements": sorted(enabled for enabled in (set(args.enabled_improvements) | (set(OPTIMIZED_IMPROVEMENTS) if args.optimized else set()))),
        "optimized_preset": bool(args.optimized),
        "mesh_columns": settings.mesh_columns,
        "mesh_rows": settings.mesh_rows,
        "cycles_samples": settings.cycles_samples,
        "reference_normalization": settings.use_reference_normalization,
        "cleanup_only": settings.cleanup_only,
        "triangulated_samples": int(np.count_nonzero(solved_mask)),
        **solver,
        "metrics": metrics.as_dict(),
    }
    (output_dir / "reconstruction_metrics.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    if args.record_reconstruction_video:
        recording_path = Path(args.record_reconstruction_video)
        stages = _build_capture_reconstruction_stages(
            metadata,
            truth=truth,
            valid_mask=valid_mask,
            object_mask=object_mask,
            reference_frames_list=reference_frames_list,
            object_frames_list=object_frames_list,
            phase_deg=settings.phase_deg,
            fringe_periods_px=[float(period) for period in settings.fringe_periods_px],
            use_reference_normalization=settings.use_reference_normalization,
            reference_projector_x=reference_projector_x,
            coarse_candidate_count=settings.solver_candidate_count,
            quadratic_subsample=settings.quadratic_subsample,
        )
        if not stages:
            stages = [
                CaptureReconstructionStage(
                    capture_index=1,
                    total_captures=1,
                    period_index=0,
                    period_count=1,
                    period_px=float(settings.fringe_periods_px[0]),
                    phase_deg=float(settings.phase_deg[0]),
                    capture_frame=object_frames_list[0][0],
                    reconstructed=reconstructed.copy(),
                    solved_mask=solved_mask.copy(),
                    metrics=metrics,
                )
            ]
        _write_reconstruction_recording(
            recording_path,
            surface_kind=str(args.surface_kind),
            stages=stages,
            truth=truth,
            final_mask=solved_mask,
            metrics=metrics,
            fps=float(args.record_fps),
        )
        result["reconstruction_recording"] = str(recording_path)
        (output_dir / "reconstruction_metrics.json").write_text(
            json.dumps(result, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(result, indent=2))

    if args.skip_thresholds:
        return 0
    if metrics.r2 < 0.99:
        raise SystemExit(f"Reconstruction verification failed: r2 too low ({metrics.r2:.4f}).")
    rmse_cm = metrics.rmse * 100.0
    if rmse_cm > 0.05:
        raise SystemExit(f"Reconstruction verification failed: rmse too high ({rmse_cm:.4f} cm).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
