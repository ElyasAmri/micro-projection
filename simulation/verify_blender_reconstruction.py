"""Orchestrator for the Blender capture + photometric reconstruction pipeline.

Drives `blender/blender_projector_capture.py` for each requested fringe period,
loads the resulting captures via `outputs.py`, solves for the height map via
`solver.py` (using `geometry.py` for the rig transforms), and writes metrics +
result images. Optionally records the four-panel acquisition video via
`recording.py`.

Verification thresholds (R2 >= 0.99, RMSE <= 0.05 cm) gate process exit unless
``--skip-thresholds`` is passed.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from outputs import (
    load_ground_truth,
    load_sequence,
    period_label,
    write_uint8,
)
import imageio.v2 as imageio  # only used for the final object_mask write
from reconstruction import (
    phase_shift_sequence,
    robust_modulation_mask,
    similarity_metrics,
)
from recording import build_pipeline_capture_stages, write_reconstruction_recording
from shared.synthetic_surfaces import SURFACE_KINDS
from solver import direct_photometric_depth_solve, reference_projector_x_map

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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify phase-shift reconstruction on the Blender synthetic scene.")
    parser.add_argument(
        "--blender-exe",
        default=r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
        help="Path to blender.exe.",
    )
    parser.add_argument(
        "--scene-script",
        default=str(Path(__file__).resolve().parent / "blender" / "blender_projector_capture.py"),
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


def _render_period(args: argparse.Namespace, settings: ImprovementSettings, period_px: float, period_dir: Path) -> int:
    """Invoke Blender to render the capture sequence for a single fringe period."""
    if period_dir.exists():
        shutil.rmtree(period_dir)
    period_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(Path(args.blender_exe)),
        "-b",
        "-P",
        str(Path(args.scene_script)),
        "--",
        "--output-dir", str(period_dir),
        "--render-width", str(args.render_width),
        "--render-height", str(args.render_height),
        "--surface-kind", str(args.surface_kind),
        "--mesh-columns", str(settings.mesh_columns),
        "--mesh-rows", str(settings.mesh_rows),
        "--cycles-samples", str(settings.cycles_samples),
        "--fringe-period-px", str(period_px),
        "--phase-deg", *[str(phase) for phase in settings.phase_deg],
    ]
    completed = subprocess.run(command, check=False)
    return completed.returncode


def main() -> int:
    args = _parse_args()
    settings = _resolve_improvement_settings(args)
    # Resolve to absolute: Blender resolves bare relative render paths against the
    # drive root (C:\out\...), not the cwd. Make every downstream path absolute.
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    period_outputs: list[Path] = []
    for period_px in settings.fringe_periods_px:
        period_dir = output_dir / f"period_{period_label(period_px)}"
        rc = _render_period(args, settings, period_px, period_dir)
        if rc != 0:
            return rc
        period_outputs.append(period_dir)

    metadata = json.loads((period_outputs[0] / "metadata.json").read_text(encoding="utf-8"))
    truth, valid_mask, object_mask = load_ground_truth(period_outputs[0])

    reference_frames_list = [load_sequence(d / "reference", "reference") for d in period_outputs]
    object_frames_list = [load_sequence(d / "object", "object") for d in period_outputs]
    reference_sequences = [phase_shift_sequence(frames) for frames in reference_frames_list]
    object_sequences = [phase_shift_sequence(frames) for frames in object_frames_list]
    modulation_mask = robust_modulation_mask(
        *[sequence.modulation for sequence in object_sequences],
        *[sequence.modulation for sequence in reference_sequences],
    )
    valid_object_mask = object_mask & valid_mask & modulation_mask
    if np.count_nonzero(valid_object_mask) < 20:
        raise ValueError("Not enough valid object samples for reconstruction verification.")

    reference_projector_x = reference_projector_x_map(metadata, valid_mask)

    reconstructed, solver_stats = direct_photometric_depth_solve(
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
    write_uint8(output_dir / "reconstruction_height.png", reconstructed, solved_mask)
    write_uint8(output_dir / "truth_height.png", truth, solved_mask)
    write_uint8(output_dir / "abs_error.png", np.abs(error), solved_mask)
    write_uint8(output_dir / "depth_error_signed.png", error, solved_mask)
    imageio.imwrite(output_dir / "object_mask.png", (solved_mask.astype(np.uint8) * 255))

    result = {
        "capture_dir": str(output_dir),
        "surface_kind": str(args.surface_kind),
        "phase_count": int(object_frames_list[0].shape[0]),
        "fringe_periods_px": [float(period) for period in settings.fringe_periods_px],
        "enabled_improvements": sorted(
            enabled for enabled in (set(args.enabled_improvements) | (set(OPTIMIZED_IMPROVEMENTS) if args.optimized else set()))
        ),
        "optimized_preset": bool(args.optimized),
        "mesh_columns": settings.mesh_columns,
        "mesh_rows": settings.mesh_rows,
        "cycles_samples": settings.cycles_samples,
        "reference_normalization": settings.use_reference_normalization,
        "cleanup_only": settings.cleanup_only,
        "triangulated_samples": int(np.count_nonzero(solved_mask)),
        **solver_stats,
        "metrics": metrics.as_dict(),
    }
    (output_dir / "reconstruction_metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    if args.record_reconstruction_video:
        recording_path = Path(args.record_reconstruction_video)
        stages = build_pipeline_capture_stages(
            metadata=metadata,
            truth=truth,
            base_mask=valid_object_mask,
            reference_frames_list=reference_frames_list,
            object_frames_list=object_frames_list,
            phase_deg=settings.phase_deg,
            fringe_periods_px=[float(period) for period in settings.fringe_periods_px],
        )
        write_reconstruction_recording(
            recording_path,
            surface_kind=str(args.surface_kind),
            stages=stages,
            truth=truth,
            final_mask=solved_mask,
            metrics=metrics,
            fps=float(args.record_fps),
        )
        result["reconstruction_recording"] = str(recording_path)
        (output_dir / "reconstruction_metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
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
