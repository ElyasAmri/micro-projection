"""Four-panel acquisition-loop video: projected fringe | capture | model so far | truth."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import imageio.v2 as imageio
import numpy as np

from geometry import fringe_pitch_mm
from outputs import colorize_scalar_map
from reconstruction import apply_height_calibration, fit_height_calibration
from solver import absolute_height_phase, psa_height_delta


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
        cv2.putText(
            canvas, subtitle, (x + 8, y + height + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (175, 186, 202), 1, cv2.LINE_AA
        )


def _capture_frame_rgb(frame: np.ndarray) -> np.ndarray:
    normalized = np.clip(np.asarray(frame, dtype=np.float64), 0.0, 1.0)
    grayscale = np.round(normalized * 255.0).astype(np.uint8)
    return np.repeat(grayscale[..., None], 3, axis=2)


def build_pipeline_capture_stages(
    *,
    metadata: dict[str, object],
    truth: np.ndarray,
    base_mask: np.ndarray,
    reference_frames_list: list[np.ndarray],
    object_frames_list: list[np.ndarray],
    phase_deg: list[float],
    fringe_periods_px: list[float],
) -> list[CaptureReconstructionStage]:
    phase_steps_rad = np.deg2rad(np.asarray(phase_deg, dtype=np.float64))
    order = sorted(range(len(fringe_periods_px)), key=lambda index: fringe_periods_px[index], reverse=True)
    periods = [float(fringe_periods_px[index]) for index in order]
    pitches_mm = [fringe_pitch_mm(metadata, period) for period in periods]
    objects = [object_frames_list[index] for index in order]
    references = [reference_frames_list[index] for index in order]
    full_counts = [sequence.shape[0] for sequence in objects]

    # Calibrate per finest-active period on the full accumulation so the displayed
    # height stays in true units as the active period changes across stages.
    calibration_by_finest: dict[int, object] = {}
    for finest in range(len(periods)):
        deltas = [
            psa_height_delta(objects[p], references[p], full_counts[p], phase_steps_rad)
            for p in range(finest + 1)
        ]
        absolute = absolute_height_phase(deltas, periods[: finest + 1], base_mask)
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
                    psa_height_delta(objects[p], references[p], counts[p], phase_steps_rad)
                    for p in active
                ]
                absolute = absolute_height_phase(deltas, [periods[p] for p in active], base_mask)
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


def write_reconstruction_recording(
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
    truth_panel = colorize_scalar_map(truth, final_mask, lo=truth_lo, hi=truth_hi)
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
                model_panel = colorize_scalar_map(stage.model_height, stage.model_mask, lo=truth_lo, hi=truth_hi)
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
