from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import imageio.v2 as imageio
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from reconstruction import (
    apply_height_calibration,
    fit_height_calibration,
    normalize_to_uint8,
    phase_shift_sequence,
    robust_modulation_mask,
    similarity_metrics,
    unwrap_phase_2d,
    wrapped_phase_delta,
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
class CaptureReconstructionStage:
    capture_index: int
    total_captures: int
    pitch_mm: float
    shift_count: int
    phase_deg: float
    projected_frame: np.ndarray
    capture_frame: np.ndarray
    model_height: np.ndarray
    model_mask: np.ndarray


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
        default=str(Path(__file__).resolve().parent / "out" / "blender_reconstruction_verify"),
        help="Directory for Blender renders and verification outputs.",
    )
    parser.add_argument("--render-width", type=int, default=1028)
    parser.add_argument("--render-height", type=int, default=752)
    parser.add_argument(
        "--surface-kind",
        default="rolling-mound",
        choices=SURFACE_KINDS,
        help="Synthetic surface profile to render in Blender. Default is slope-bounded "
             "so the surface never self-shadows the projection.",
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


def _psa_height_delta(
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


def _absolute_height_phase(
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


def _build_pipeline_capture_stages(
    *,
    metadata: dict[str, object],
    truth: np.ndarray,
    base_mask: np.ndarray,
    reference_frames_list: list[np.ndarray],
    object_frames_list: list[np.ndarray],
    phase_deg: list[float],
    fringe_periods_px: list[float],
) -> list[CaptureReconstructionStage]:
    """Per-capture acquisition stages: each captured fringe is folded into the
    model via additive phase-shift accumulation, periods introduced coarse->fine
    so the model appears early and sharpens in place."""
    phase_steps_rad = np.deg2rad(np.asarray(phase_deg, dtype=np.float64))
    order = sorted(range(len(fringe_periods_px)), key=lambda index: fringe_periods_px[index], reverse=True)
    periods = [float(fringe_periods_px[index]) for index in order]
    pitches_mm = [_fringe_pitch_mm(metadata, period) for period in periods]
    objects = [object_frames_list[index] for index in order]
    references = [reference_frames_list[index] for index in order]
    full_counts = [sequence.shape[0] for sequence in objects]

    # Calibrate per finest-active period on the full accumulation so the displayed
    # height stays in true units as the active period changes across stages.
    calibration_by_finest: dict[int, object] = {}
    for finest in range(len(periods)):
        deltas = [
            _psa_height_delta(objects[p], references[p], full_counts[p], phase_steps_rad)
            for p in range(finest + 1)
        ]
        absolute = _absolute_height_phase(deltas, periods[: finest + 1], base_mask)
        calibration_by_finest[finest] = fit_height_calibration(
            absolute, truth, base_mask, include_spatial_terms=True
        )

    total_captures = int(sum(full_counts))
    counts = [0] * len(periods)
    stages: list[CaptureReconstructionStage] = []
    capture_index = 0
    for finest in range(len(periods)):
        for phase_index in range(objects[finest].shape[0]):
            counts[finest] += 1
            capture_index += 1
            active = [p for p in range(len(counts)) if counts[p] >= 3]
            model_height = np.full(base_mask.shape, np.nan, dtype=np.float64)
            model_mask = np.zeros(base_mask.shape, dtype=bool)
            if active:
                deltas = [
                    _psa_height_delta(objects[p], references[p], counts[p], phase_steps_rad)
                    for p in active
                ]
                absolute = _absolute_height_phase(deltas, [periods[p] for p in active], base_mask)
                model_height = apply_height_calibration(absolute, calibration_by_finest[active[-1]])
                model_mask = base_mask.copy()
            stages.append(
                CaptureReconstructionStage(
                    capture_index=capture_index,
                    total_captures=total_captures,
                    pitch_mm=pitches_mm[finest],
                    shift_count=counts[finest],
                    phase_deg=float(phase_deg[phase_index]),
                    projected_frame=references[finest][phase_index],
                    capture_frame=objects[finest][phase_index],
                    model_height=model_height,
                    model_mask=model_mask,
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
    truth_panel = _colorize_scalar_map(truth, final_mask, lo=truth_lo, hi=truth_hi)
    blank_panel = np.full((*truth.shape, 3), (14, 14, 18), dtype=np.uint8)

    canvas_w, canvas_h = 1640, 720
    panel_w = panel_h = 360
    panel_xs = (36, 436, 836, 1236)
    panel_y = 190
    margin = 36

    writer = imageio.get_writer(str(output_path), fps=fps, macro_block_size=None)
    try:
        for hold_index, stage in enumerate([stages[0], *stages, stages[-1], stages[-1]]):
            if np.any(stage.model_mask):
                model_panel = _colorize_scalar_map(stage.model_height, stage.model_mask, lo=truth_lo, hi=truth_hi)
            else:
                model_panel = blank_panel

            frame = np.full((canvas_h, canvas_w, 3), (8, 10, 14), dtype=np.uint8)
            cv2.putText(
                frame,
                f"Fringe projection profilometry - {surface_kind.replace('-', ' ')}",
                (margin, 44),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.85,
                (236, 240, 246),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                frame,
                (
                    f"Capture {stage.capture_index:02d}/{stage.total_captures:02d}"
                    f"  |  Fringe pitch {stage.pitch_mm:.0f} mm  shift {stage.shift_count:02d}"
                    f"  |  phase {stage.phase_deg:.1f} deg"
                ),
                (margin, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (184, 194, 208),
                1,
                cv2.LINE_AA,
            )
            for x, image, title, subtitle in (
                (panel_xs[0], _capture_frame_rgb(stage.projected_frame), "Projected fringe", "pattern shifts each frame"),
                (panel_xs[1], _capture_frame_rgb(stage.capture_frame), "Camera capture", "fringe imaged on the object"),
                (panel_xs[2], model_panel, "Model so far", "captures applied via phase-shift"),
                (panel_xs[3], truth_panel, "Ground truth", "reference height map"),
            ):
                _draw_panel(frame, image, x=x, y=panel_y, width=panel_w, height=panel_h, title=title, subtitle=subtitle)

            bar_x, bar_y = margin, 600
            bar_w = canvas_w - 2 * margin
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + 22), (24, 28, 36), thickness=-1)
            progress = stage.capture_index / max(1, stage.total_captures)
            cv2.rectangle(
                frame,
                (bar_x, bar_y),
                (bar_x + int(round(bar_w * progress)), bar_y + 22),
                (70, 160, 250),
                thickness=-1,
            )
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + 22), (58, 66, 82), thickness=1)
            cv2.putText(
                frame,
                f"Final solve benchmark: R2={metrics.r2:.4f}  RMSE={metrics.rmse * 1000.0:.3f} mm",
                (margin, 664),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (170, 180, 196),
                1,
                cv2.LINE_AA,
            )

            repeat = max(2, int(round(fps * 0.75))) if (hold_index == 0 or hold_index > len(stages)) else 1
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


def _capture_rays_from_pixels(
    metadata: dict[str, object],
    xs: np.ndarray,
    ys: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-pixel ray origins plus the single shared ray direction.

    The capture camera is orthographic, so every ray shares one direction and only
    the origin varies across the sensor -- the whole pixel grid resolves in one
    vectorized transform instead of a Python loop.
    """
    width = int(metadata["render_width"])
    height = int(metadata["render_height"])
    min_x, max_x, min_y, max_y, _ = _frame_bounds_from_metadata(
        metadata,
        "capture_camera_frame_bounds_local",
    )
    camera_matrix = _matrix_from_rows(metadata["capture_camera_matrix_world"])
    nx = (np.asarray(xs, dtype=np.float64) + 0.5) / width
    ny = 1.0 - ((np.asarray(ys, dtype=np.float64) + 0.5) / height)
    local = np.stack(
        [min_x + (max_x - min_x) * nx, min_y + (max_y - min_y) * ny, np.zeros_like(nx)],
        axis=1,
    )
    origins = local @ camera_matrix[:3, :3].T + camera_matrix[:3, 3]
    direction = _normalize(_transform_direction(camera_matrix, np.array([0.0, 0.0, -1.0], dtype=np.float64)))
    return origins, direction


def _plane_geometry(metadata: dict[str, object]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    plane_matrix = _matrix_from_rows(metadata["plane_matrix_world"])
    plane_center = _transform_point(plane_matrix, np.array([0.0, 0.0, 0.0], dtype=np.float64))
    plane_right = _normalize(_transform_direction(plane_matrix, np.array([1.0, 0.0, 0.0], dtype=np.float64)))
    plane_up = _normalize(_transform_direction(plane_matrix, np.array([0.0, 1.0, 0.0], dtype=np.float64)))
    plane_normal = _normalize(_transform_direction(plane_matrix, np.array([0.0, 0.0, 1.0], dtype=np.float64)))
    return plane_center, plane_right, plane_up, plane_normal


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


def _fringe_pitch_mm(metadata: dict[str, object], period_proj_px: float) -> float:
    """Physical pitch of one fringe period on the reference plane, in mm.

    Converts the device-native projector-pixel period to a real-world distance on
    the measurement plane (view-independent), via the projector frustum geometry.
    """
    plane_center, plane_right, _, _ = _plane_geometry(metadata)
    probe_m = 0.05
    x0 = _project_world_to_projector_x(plane_center, metadata)
    x1 = _project_world_to_projector_x(plane_center + plane_right * probe_m, metadata)
    mm_per_projector_px = (probe_m * 1000.0) / abs(x1 - x0)
    return period_proj_px * mm_per_projector_px


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
    ys, xs = np.where(valid_mask)
    if xs.size == 0:
        return projector_x
    origins, direction = _capture_rays_from_pixels(metadata, xs, ys)
    denominator = float(np.dot(direction, plane_normal))
    if abs(denominator) <= 1e-12:
        return projector_x
    distance = (plane_center - origins) @ plane_normal / denominator
    hits = origins + distance[:, None] * direction[None, :]
    good = distance > 1e-9
    if np.any(good):
        projector_x[ys[good], xs[good]] = _projector_x_from_world_points(hits[good], metadata)
    return projector_x


def _prepare_camera_ray_geometry(
    metadata: dict[str, object],
    mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    plane_center, _, _, plane_normal = _plane_geometry(metadata)
    ys, xs = np.where(mask)
    origins, direction = _capture_rays_from_pixels(metadata, xs, ys)
    denominator = float(np.dot(direction, plane_normal))
    plane_t = (plane_center - origins) @ plane_normal / denominator
    plane_hits = origins + plane_t[:, None] * direction[None, :]
    ray_coefficients = np.broadcast_to(direction / denominator, origins.shape).copy()
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
        solved_depth[start:end] = best_depth
        reconstructed[ys[start:end], xs[start:end]] = best_depth

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
    # Resolve to absolute: Blender resolves bare relative render paths against the
    # drive root (C:\out\...), not the cwd. Make every downstream path absolute.
    output_dir = Path(args.output_dir).resolve()
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
        stages = _build_pipeline_capture_stages(
            metadata=metadata,
            truth=truth,
            base_mask=valid_object_mask,
            reference_frames_list=reference_frames_list,
            object_frames_list=object_frames_list,
            phase_deg=settings.phase_deg,
            fringe_periods_px=[float(period) for period in settings.fringe_periods_px],
        )
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
