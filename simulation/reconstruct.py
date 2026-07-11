"""Phase extraction, height reconstruction, and ground-truth comparison.

Loads the N-step phase-shifted capture stack (capture_pipeline.py), extracts
phase via the N-step PSA (report/math.tex, "N-step phase-shifting
algorithm"), converts phase to height via this rig's phase-to-height
relation (report/math.tex, "Height from phase, for this rig's geometry"),
and compares the result against a known ground-truth surface (surfaces.py).

Pure numpy/opencv on the rendered PNG frames -- no bpy/Blender needed here:
    .venv/bin/python3 simulation/reconstruct.py \
        --capture-dir out/capture --out-dir out/reconstruction \
        --surface bump --n-periods 8
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np

import exposure
import occlusion
import surfaces
from geometry_constants import H0_MM, N_PERIODS_LADDER, THETA_DEG, W0_MM, W_PROJ_MM


def load_frames(capture_dir: Path) -> np.ndarray:
    paths = sorted(capture_dir.glob("frame_*.png"))
    if not paths:
        raise FileNotFoundError(f"no frame_*.png files in {capture_dir}")
    frames = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE).astype(np.float64) / 255.0 for p in paths]
    return np.stack(frames, axis=0)  # (N, H, W)


def extract_phase(frames: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """N-step PSA (report/math.tex Eq. nstep-psa). Returns (phase, modulation)."""
    n = frames.shape[0]
    delta = 2.0 * np.pi * np.arange(n) / n
    cos_d = np.cos(delta)[:, None, None]
    sin_d = np.sin(delta)[:, None, None]
    c = np.sum(frames * cos_d, axis=0)
    s = np.sum(frames * sin_d, axis=0)
    phase = np.arctan2(-s, c)
    modulation = (2.0 / n) * np.hypot(c, s)
    return phase, modulation


def wrap_to_pi(x: np.ndarray) -> np.ndarray:
    return (x + np.pi) % (2.0 * np.pi) - np.pi


def pixel_to_world(shape: tuple[int, int], theta_deg: float) -> tuple[np.ndarray, np.ndarray]:
    """World (x, y) mm each pixel images on the *flat reference* plane
    (report/math.tex, "Height from phase" derivation's camera-side ray map).

    Ray-traced from the camera's actual matrix_world (read back directly
    with rig.add_telecentric_camera()'s object, not assumed): columns run
    along the tilted (world x-z) direction with the 1/cos(theta) widening,
    rows run directly along world y, unaffected by tilt.
    """
    h_px, w_px = shape
    theta = math.radians(theta_deg)
    cols = np.arange(w_px)
    rows = np.arange(h_px)
    lr = (cols + 0.5) / w_px * W0_MM - W0_MM / 2.0
    lu = (rows + 0.5) / h_px * H0_MM - H0_MM / 2.0
    lr_grid, lu_grid = np.meshgrid(lr, lu)  # (H, W)
    world_x = -lr_grid / math.cos(theta)
    world_y = lu_grid
    return world_x, world_y


def pixel_pitch_mm(shape: tuple[int, int], theta_deg: float) -> tuple[float, float]:
    """Per-axis world pixel pitch (dx, dy) in mm for the reconstruction grid.
    The grid is uniform per axis (pixel_to_world), so a single dx/dy describes
    it -- what roughness's areal filter needs to size its cutoff in mm."""
    world_x, world_y = pixel_to_world(shape, theta_deg)
    dx = float(abs(world_x[0, 1] - world_x[0, 0])) if shape[1] > 1 else 0.0
    dy = float(abs(world_y[1, 0] - world_y[0, 0])) if shape[0] > 1 else 0.0
    return dx, dy


def carrier_phase(world_x: np.ndarray, n_periods: float) -> np.ndarray:
    """phi_carrier: what the N-step PSA would measure at each pixel for a
    flat (h=0) reference, computed analytically from known rig geometry
    (report/math.tex Eq. intensity at z=0), not a separate calibration
    capture. The -pi/2 constant (sin- vs. cos-basis offset, report/math.tex
    "N-step phase-shifting algorithm") is included so it cancels exactly
    against phi_measured's own offset when forming psi."""
    u_flat = world_x / W_PROJ_MM + 0.5
    big_phi = 2.0 * np.pi * n_periods * u_flat
    return wrap_to_pi(big_phi - np.pi / 2.0)


def psi_from_frames(
    frames: np.ndarray, n_periods: float, world_x: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Wrapped surface phase psi (in (-pi, pi]) and modulation for one frequency.

    Runs the N-step PSA on `frames`, subtracts this frequency's analytic carrier
    phase (the flat-reference phase, carrier_phase()), and wraps the difference.
    psi is the object's phase relative to the flat plane -- what phase-to-height
    (single frequency, run()) or unwrap_multifreq (a ladder) consumes."""
    phase, modulation = extract_phase(frames)
    phi_carrier = carrier_phase(world_x, n_periods)
    psi = wrap_to_pi(phase - phi_carrier)
    return psi, modulation


def _valid_mask(modulation: np.ndarray, threshold: float, erode_px: int) -> np.ndarray:
    """Well-modulated pixels, shrunk inward by `erode_px` to drop the field
    boundaries where the modulation tapers off."""
    valid = modulation > threshold
    if erode_px > 0:
        valid = cv2.erode(valid.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=erode_px).astype(bool)
    return valid


def equivalent_wavelength_mm(n_periods: float, theta_deg: float) -> float:
    """lambda_eq (mm); h = psi/(2*pi) * lambda_eq (report/math.tex Eq.
    height-from-phase).

    A position-dependent refinement (p_eff/(tan(theta) + x/D), correcting
    for the projector's own perspective divide off-center) was tried and
    reverted: checked directly against the actual per-pixel bias in a
    captured surface rather than trusting the top-line RMSE, that formula
    predicts a bias 6-10x smaller than what's actually there, peaking at a
    different position than it predicts (|x| ~= 24mm, not sigma=15mm) --
    i.e. it's a real but secondary effect, not the dominant one, and
    correcting only it made two of six surfaces worse (see
    report/math.tex "Off-center bias" for the follow-up investigation)."""
    p_eff = W_PROJ_MM / n_periods
    return p_eff / math.tan(math.radians(theta_deg))


def unwrap_2d_spatial(wrapped: np.ndarray) -> np.ndarray:
    """Goldstein branch-cut spatial unwrap (scikit-image), for a lone
    single-frequency capture where no multi-frequency ladder is available.
    The ladder (unwrap_multifreq) is the primary path; this is the fallback.
    Lazy import: scikit-image is not a base requirement."""
    try:
        from skimage.restoration import unwrap_phase
    except ImportError as exc:
        raise ImportError("unwrap_2d_spatial needs scikit-image: "
                          "pip install scikit-image") from exc
    return np.asarray(unwrap_phase(wrapped), dtype=np.float64)


def unwrap_multifreq(psis: list[np.ndarray], lambdas: list[float]) -> np.ndarray:
    """Coarse-to-fine temporal phase unwrapping -> absolute height (mm).

    `psis` are the per-frequency wrapped surface phases psi_i (each in (-pi, pi],
    from psi_from_frames), ordered coarsest first; `lambdas` are the matching
    equivalent wavelengths lambda_eq_i (mm), strictly decreasing.

    Each rung on its own only measures height modulo lambda_eq_i (the wrapped
    h = psi/2pi * lambda_eq). The coarsest is taken at face value -- it must be
    unambiguous over the surface, |h| < lambda_eq_0/2 -- and every finer rung's
    integer fringe order k is chosen so its continuous phase agrees with the
    running (coarser) height estimate:

        k = round( (2*pi*h_coarse/lambda_eq - psi) / 2*pi )
        h = (psi/2*pi + k) * lambda_eq

    The finest rung's height is returned: highest resolution, ambiguity removed.
    Correct as long as each step's guide is within +/- lambda_eq_i/2 of the truth
    -- hence the modest ratios in geometry_constants.N_PERIODS_LADDER."""
    if len(psis) != len(lambdas):
        raise ValueError(f"psis ({len(psis)}) and lambdas ({len(lambdas)}) length mismatch")
    if not psis:
        raise ValueError("need at least one frequency")
    if any(lambdas[i] <= lambdas[i + 1] for i in range(len(lambdas) - 1)):
        raise ValueError(f"lambdas must be strictly decreasing (coarse -> fine): {lambdas}")

    height = psis[0] / (2.0 * np.pi) * lambdas[0]
    for psi, lam in zip(psis[1:], lambdas[1:]):
        predicted_phase = 2.0 * np.pi * height / lam
        k = np.round((predicted_phase - psi) / (2.0 * np.pi))
        height = (psi / (2.0 * np.pi) + k) * lam
    return height


def colorize(value: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
    span = vmax - vmin
    norm = np.clip((value - vmin) / span, 0.0, 1.0) if span > 0 else np.zeros_like(value)
    gray = (norm * 255).astype(np.uint8)
    return cv2.applyColorMap(gray, cv2.COLORMAP_TURBO)


def _write_and_score(
    height: np.ndarray,
    valid: np.ndarray,
    world_x: np.ndarray,
    world_y: np.ndarray,
    out_dir: Path,
    surface: str | None,
    metrics: dict,
    verbose: bool,
) -> dict:
    """Score `height` against ground truth (when `surface` is a known specimen),
    write the visualizations (height always; ground-truth + error only when
    scored) and metrics.txt. Shared by run() and run_multifreq(); `metrics` is
    updated in place with rmse/mae/max_abs/r2 when scored, and returned.

    `metrics["lambda_eq_mm"]` (the final-resolution wavelength) is used only for
    the verbose print."""
    ground_truth_fn = surfaces.SURFACES[surface] if surface is not None else None
    lambda_eq = metrics.get("lambda_eq_mm", float("nan"))

    # Persist the raw height + mask (and the per-axis pixel pitch) so downstream
    # tools -- roughness.py above all -- consume the height map without redoing
    # the reconstruction. The grid is uniform per axis (pixel_to_world), so a
    # single dx/dy describes it.
    np.save(out_dir / "height.npy", height)
    np.save(out_dir / "valid.npy", valid)
    dx_mm, dy_mm = pixel_pitch_mm(height.shape, THETA_DEG)
    metrics["dx_mm"], metrics["dy_mm"] = dx_mm, dy_mm

    if ground_truth_fn is not None:
        ground_truth = ground_truth_fn(world_x, world_y)
        error = height - ground_truth
        # Shadow-aware scoring: exclude pixels the camera physically cannot
        # see (terrain self-occlusion, known exactly for a synthetic
        # specimen). Bounce light gives them enough modulation to pass the
        # instrument mask, but their phase is unmeasurable garbage -- scoring
        # them mixes a physics limit into reconstruction quality. The
        # instrument mask (valid.npy) is untouched; the oracle mask is saved
        # alongside it.
        hidden = occlusion.camera_hidden_mask(ground_truth, world_x, dx_mm)
        np.save(out_dir / "camera_hidden.npy", hidden)
        metrics["camera_hidden_pct"] = 100.0 * float(hidden.mean())
        score = valid & ~hidden
        err_valid = error[score]
        gt_valid = ground_truth[score]
        rmse = float(np.sqrt(np.mean(err_valid ** 2)))
        mae = float(np.mean(np.abs(err_valid)))
        max_abs = float(np.max(np.abs(err_valid)))
        gt_var = float(np.sum((gt_valid - gt_valid.mean()) ** 2))
        r2 = float(1.0 - np.sum(err_valid ** 2) / gt_var) if gt_var > 1e-12 else float("nan")
        metrics.update({"rmse": rmse, "mae": mae, "max_abs": max_abs, "r2": r2})

        if verbose:
            print(f"lambda_eq = {lambda_eq:.3f} mm")
            if hidden.any():
                print(f"camera-hidden (excluded from scoring): "
                      f"{metrics['camera_hidden_pct']:.2f}% of the field")
            print(f"RMSE = {rmse:.4f} mm, MAE = {mae:.4f} mm, max|err| = {max_abs:.4f} mm, R^2 = {r2:.4f}")

        gt_span = gt_valid.max() - gt_valid.min()
        vmin, vmax = float(gt_valid.min()), float(gt_valid.max())
        if gt_span < 1e-9:  # flat surface: give the colormap a non-zero window to render in
            vmin, vmax = -0.05, 0.05
        height_masked = np.where(valid, height, np.nan)
        cv2.imwrite(str(out_dir / "height_reconstructed.png"), colorize(np.nan_to_num(height_masked, nan=vmin), vmin, vmax))
        cv2.imwrite(str(out_dir / "height_ground_truth.png"), colorize(np.where(valid, ground_truth, vmin), vmin, vmax))
        err_abs_max = max(float(np.abs(err_valid).max()), 1e-9)
        err_masked = np.where(score, error, 0.0)
        cv2.imwrite(str(out_dir / "height_error.png"), colorize(err_masked, -err_abs_max, err_abs_max))
    else:
        # No ground truth (real capture): render the height map over its own
        # valid range, and skip the ground-truth / error maps entirely.
        if valid.any():
            h_valid = height[valid]
            vmin, vmax = float(np.percentile(h_valid, 1)), float(np.percentile(h_valid, 99))
        else:
            vmin, vmax = -0.05, 0.05
        if vmax - vmin < 1e-9:
            vmin, vmax = vmin - 0.05, vmax + 0.05
        if verbose:
            print(f"lambda_eq = {lambda_eq:.3f} mm (no ground truth; height map only)")
        height_masked = np.where(valid, height, np.nan)
        cv2.imwrite(str(out_dir / "height_reconstructed.png"), colorize(np.nan_to_num(height_masked, nan=vmin), vmin, vmax))

    with open(out_dir / "metrics.txt", "w") as f:
        for key, value in metrics.items():
            f.write(f"{key}: {value}\n")
    return metrics


def run(
    capture_dir: Path,
    out_dir: Path,
    n_periods: float = 8.0,
    surface: str | None = "bump",
    modulation_threshold: float = 0.03,
    erode_px: int = 10,
    normalize_gains: bool = True,
    verbose: bool = True,
) -> dict:
    """Reconstruct height from a capture stack. When `surface` names a known
    specimen, score the result against surfaces.SURFACES[surface]'s exact
    ground truth (RMSE/R^2 + ground-truth and error maps). When `surface` is
    None (a real-world capture with no ground truth), just produce the height
    map. Returns a metrics dict and writes visualizations + metrics.txt.

    `normalize_gains` (on by default) divides out any per-frame brightness swing
    before the PSA, so auto-exposure drift doesn't ripple into the height map;
    it's a no-op on a steady stack (see exposure.py). The measured swing is
    reported either way."""
    out_dir.mkdir(parents=True, exist_ok=True)

    frames = load_frames(capture_dir)
    swing_pct = exposure.brightness_swing_pct(frames)
    if normalize_gains:
        frames, _gains = exposure.normalize_frame_gains(frames)
    n, h_px, w_px = frames.shape
    if verbose:
        print(f"loaded {n} frames of shape {h_px}x{w_px}")

    world_x, world_y = pixel_to_world((h_px, w_px), THETA_DEG)
    psi, modulation = psi_from_frames(frames, n_periods, world_x)
    valid = _valid_mask(modulation, modulation_threshold, erode_px)
    if verbose:
        print(f"valid (masked) pixels: {valid.sum()} / {valid.size} ({100 * valid.mean():.1f}%)")

    lambda_eq = equivalent_wavelength_mm(n_periods, THETA_DEG)
    height = psi / (2.0 * np.pi) * lambda_eq

    metrics = {
        "surface": surface,
        "frames": n,
        "valid_pixels": int(valid.sum()),
        "total_pixels": int(valid.size),
        "lambda_eq_mm": lambda_eq,
        "brightness_swing_pct": swing_pct,
    }
    metrics = _write_and_score(height, valid, world_x, world_y, out_dir, surface, metrics, verbose)
    if verbose:
        print(f"wrote outputs to {out_dir}")
    return metrics


def run_multifreq(
    capture_dirs: list[Path],
    out_dir: Path,
    n_periods_ladder: list[float] | None = None,
    surface: str | None = "bump",
    modulation_threshold: float = 0.03,
    erode_px: int = 10,
    normalize_gains: bool = True,
    verbose: bool = True,
) -> dict:
    """Reconstruct height from a coarse-to-fine ladder of capture stacks.

    `capture_dirs` are the per-frequency frame directories, coarsest first,
    matching `n_periods_ladder` (defaults to geometry_constants.N_PERIODS_LADDER).
    Each stack becomes a wrapped surface phase (psi_from_frames); the ladder is
    then temporally unwrapped (unwrap_multifreq), recovering the finest rung's
    resolution without its 2*pi ambiguity. A pixel is trusted only where *every*
    rung is well modulated (the per-rung masks are intersected). Scoring, outputs
    and metrics otherwise match run(); the reported lambda_eq_mm is the finest
    (resolution) rung, lambda_eq_coarse_mm the coarsest (unambiguous range).

    This is the roughness path's backbone: the coarse rung fixes the range, the
    fine rung the resolution (the multi-frequency method of the Chapter 3 paper;
    report/math.tex will document the ladder as part of Phase 2)."""
    if n_periods_ladder is None:
        n_periods_ladder = list(N_PERIODS_LADDER)
    capture_dirs = [Path(d) for d in capture_dirs]
    if len(capture_dirs) != len(n_periods_ladder):
        raise ValueError(f"got {len(capture_dirs)} capture dirs for {len(n_periods_ladder)} ladder rungs")
    if len(capture_dirs) < 2:
        raise ValueError("multi-frequency reconstruction needs >= 2 rungs; use run() for a single frequency")
    if any(n_periods_ladder[i] >= n_periods_ladder[i + 1] for i in range(len(n_periods_ladder) - 1)):
        raise ValueError(f"n_periods_ladder must be strictly increasing (coarse -> fine): {n_periods_ladder}")
    out_dir.mkdir(parents=True, exist_ok=True)

    psis: list[np.ndarray] = []
    lambdas: list[float] = []
    valid: np.ndarray | None = None
    world_x = world_y = None
    swing_pct = 0.0
    n_frames = None
    shape0 = None
    for capture_dir, n_periods in zip(capture_dirs, n_periods_ladder):
        frames = load_frames(capture_dir)
        swing_pct = max(swing_pct, exposure.brightness_swing_pct(frames))
        if normalize_gains:
            frames, _gains = exposure.normalize_frame_gains(frames)
        n, h_px, w_px = frames.shape
        if shape0 is None:
            shape0, n_frames = (h_px, w_px), n
            world_x, world_y = pixel_to_world(shape0, THETA_DEG)
        elif (h_px, w_px) != shape0:
            raise ValueError(f"ladder rung {capture_dir} is {h_px}x{w_px}, expected {shape0[0]}x{shape0[1]}")

        psi, modulation = psi_from_frames(frames, n_periods, world_x)
        rung_valid = _valid_mask(modulation, modulation_threshold, erode_px)
        valid = rung_valid if valid is None else (valid & rung_valid)
        psis.append(psi)
        lambdas.append(equivalent_wavelength_mm(n_periods, THETA_DEG))

    height = unwrap_multifreq(psis, lambdas)
    lambda_coarse, lambda_fine = lambdas[0], lambdas[-1]

    metrics = {
        "surface": surface,
        "n_periods_ladder": list(n_periods_ladder),
        "rungs": len(capture_dirs),
        "frames_per_rung": n_frames,
        "valid_pixels": int(valid.sum()),
        "total_pixels": int(valid.size),
        "lambda_eq_mm": lambda_fine,           # final vertical-resolution rung
        "lambda_eq_coarse_mm": lambda_coarse,  # unambiguous-range rung
        "unambiguous_range_mm": lambda_coarse / 2.0,
        "brightness_swing_pct": swing_pct,
    }
    if verbose:
        print(f"multi-frequency ladder {list(n_periods_ladder)}: "
              f"lambda_eq {lambda_coarse:.3f} -> {lambda_fine:.3f} mm "
              f"(unambiguous +/- {lambda_coarse / 2.0:.2f} mm)")
        print(f"valid (masked) pixels: {valid.sum()} / {valid.size} ({100 * valid.mean():.1f}%)")
    metrics = _write_and_score(height, valid, world_x, world_y, out_dir, surface, metrics, verbose)
    if verbose:
        print(f"wrote outputs to {out_dir}")
    return metrics


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-dir", default="out/capture", type=Path)
    parser.add_argument("--out-dir", default="out/reconstruction", type=Path)
    parser.add_argument("--n-periods", default=8.0, type=float)
    parser.add_argument("--surface", default="bump", choices=sorted(surfaces.SURFACES))
    parser.add_argument("--modulation-threshold", default=0.03, type=float)
    parser.add_argument("--erode-px", default=10, type=int, help="shrink the valid mask inward by this many pixels, away from field boundaries")
    parser.add_argument("--capture-dirs", nargs="+", type=Path, default=None,
                        help="coarse->fine per-frequency stacks; enables multi-frequency unwrapping (overrides --capture-dir)")
    parser.add_argument("--n-periods-ladder", nargs="+", type=float, default=None,
                        help="fringe counts matching --capture-dirs (default: geometry_constants.N_PERIODS_LADDER)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.capture_dirs:
        run_multifreq(
            args.capture_dirs,
            args.out_dir,
            n_periods_ladder=args.n_periods_ladder,
            surface=args.surface,
            modulation_threshold=args.modulation_threshold,
            erode_px=args.erode_px,
        )
    else:
        run(
            args.capture_dir,
            args.out_dir,
            n_periods=args.n_periods,
            surface=args.surface,
            modulation_threshold=args.modulation_threshold,
            erode_px=args.erode_px,
        )


if __name__ == "__main__":
    main()
