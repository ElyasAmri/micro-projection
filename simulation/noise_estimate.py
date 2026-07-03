"""Noise estimation, and what camera noise does to a reconstruction.

A companion to reconstruct.py. Instead of turning a fringe stack into a height
map, this estimates the imaging noise in the stack and propagates it into a
per-pixel height uncertainty -- the error margin the reconstruction inherits
from the camera. Two experiments, mirroring reconstruct.py's sim-vs-real split:

  * inject a KNOWN noise level into a synthetic stack, estimate it, and check
    the estimate (the noise analogue of the ground-truth validation battery);
  * estimate the noise in a REAL capture, where there's no known truth.

Estimator (temporal). For an N-step phase-shift stack every pixel follows
I_k = a + b*cos(phi + 2*pi*k/N), a sinusoid in the phase step that (fundamental
plus a couple of harmonics) is linear in its unknowns, so the least-squares fit
is the closed-form PSA (report/math.tex). The residual between the measured
samples and that fitted sinusoid is an unbiased per-pixel estimate of the noise
sigma. Fitting the 2nd harmonic as well keeps a mildly non-sinusoidal fringe
(projector gamma) from leaking into the residual. Pixels that clip (a saturated
or black sample) are excluded -- clipping is not noise, and it breaks the fit.

Estimator (spatial). Immerkaer's Laplacian estimate on each frame is reported
as an independent, single-frame cross-check. The temporal estimator sees every
frame-to-frame deviation from the model (random noise *and* any systematic
inconsistency such as phase-step error); the spatial one sees only within-frame
pixel noise. When the two diverge sharply, the stack has a systematic error, not
just noise -- which is itself worth knowing.

Propagation. For the N-step PSA the phase noise is sigma_phi = sigma_I *
sqrt(2/N) / b, so the height uncertainty is sigma_h = (lambda_eq / 2*pi) *
sigma_phi. It blows up where the modulation b is weak (dim or washed-out
fringes) -- exactly where a real reconstruction is least trustworthy -- which is
why the error margin is a map, not a single number.

    .venv/bin/python3 simulation/noise_estimate.py \
        --capture-dir out/surface_tests/bump/capture \
        --out-dir out/noise --surface bump --n-periods 8
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np

import reconstruct
import surfaces
from geometry_constants import THETA_DEG

# Immerkaer's noise mask: a Laplacian that a smooth image passes near zero, so
# its response is dominated by pixel noise.
_LAPLACIAN = np.array([[1.0, -2.0, 1.0], [-2.0, 4.0, -2.0], [1.0, -2.0, 1.0]])

# 8-bit quantization adds its own noise floor of 1LSB/sqrt(12); estimates can't
# go below it, and injected-vs-estimated comparisons must account for it.
QUANT_SIGMA = (1.0 / 255.0) / math.sqrt(12.0)


def fit_residual_sigma(frames: np.ndarray, n_harm: int | None = None) -> np.ndarray:
    """Per-pixel noise sigma from the residual of the phase-stack sinusoid fit.
    `frames` is (N, H, W) in [0, 1]; returns an (H, W) sigma map (normalized).

    The model is DC + `n_harm` harmonics of the phase step -- the fundamental
    plus, by default, the 2nd harmonic, so a *mildly* non-sinusoidal fringe
    (projector gamma, a touch of harmonic distortion) doesn't leak into the
    residual and inflate the estimate. For evenly spaced steps over a full
    period the basis is orthogonal, so the fit is the closed-form DFT (no
    solve). Anything the model can't represent -- random noise, but also any
    systematic frame-to-frame inconsistency -- lands in the residual; compare
    against the spatial estimate to tell the two apart."""
    n = frames.shape[0]
    if n < 4:
        raise ValueError("need >= 4 phase steps to estimate noise from the fit residual")
    max_h = (n - 1) // 2  # need 2*h < N for the h-th harmonic to be independent
    if n_harm is None:
        n_harm = min(2, max_h)
    n_harm = max(1, min(n_harm, max_h))

    delta = 2.0 * np.pi * np.arange(n) / n
    model = np.broadcast_to(frames.mean(axis=0), frames.shape).copy()  # DC
    n_params = 1
    for h in range(1, n_harm + 1):
        cos_h = np.cos(h * delta)[:, None, None]
        sin_h = np.sin(h * delta)[:, None, None]
        p = (2.0 / n) * np.sum(frames * cos_h, axis=0)
        q = (2.0 / n) * np.sum(frames * sin_h, axis=0)
        model = model + p[None, :, :] * cos_h + q[None, :, :] * sin_h
        n_params += 2
    resid = frames - model
    return np.sqrt(np.sum(resid ** 2, axis=0) / (n - n_params))


def immerkaer_sigma(frame: np.ndarray) -> float:
    """Single-frame noise sigma (normalized) via Immerkaer's Laplacian."""
    conv = cv2.filter2D(frame, -1, _LAPLACIAN, borderType=cv2.BORDER_REPLICATE)
    h, w = frame.shape
    return math.sqrt(math.pi / 2.0) / (6.0 * (w - 2) * (h - 2)) * float(np.sum(np.abs(conv[1:-1, 1:-1])))


def synth_noisy_stack(
    out_dir: Path,
    surface: str,
    n_periods: float = 8.0,
    n_steps: int = 8,
    sigma: float = 5.0 / 255.0,
    exposure: float = 1.0,
    shape: tuple[int, int] = (512, 640),
    seed: int = 0,
) -> dict:
    """Write an N-step phase-shift stack of `surface` with a KNOWN additive
    Gaussian noise `sigma` (normalized) -- the "project frames with a certain
    noise level" step. The clean fringe is the exact forward model of
    reconstruct.py (carrier phase + the surface's height-to-phase term), so the
    same stack round-trips through reconstruct.run() back to the surface, and
    the injected noise is the only error. `exposure` scales the DC + modulation
    (a proxy for under/over-exposure); values that push the fringe past 1.0
    clip, so over-exposure shows up as saturated pixels."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    world_x, world_y = reconstruct.pixel_to_world(shape, THETA_DEG)
    lambda_eq = reconstruct.equivalent_wavelength_mm(n_periods, THETA_DEG)
    height = surfaces.SURFACES[surface](world_x, world_y)
    carrier = reconstruct.carrier_phase(world_x, n_periods)
    phi = carrier + height * 2.0 * np.pi / lambda_eq

    a = 0.5 * exposure
    b = 0.45 * exposure
    for k in range(n_steps):
        delta = 2.0 * np.pi * k / n_steps
        clean = a + b * np.cos(phi + delta)
        noisy = np.clip(clean + rng.normal(0.0, sigma, shape), 0.0, 1.0)
        cv2.imwrite(str(out_dir / f"frame_{k:02d}.png"), (noisy * 255.0).astype(np.uint8))
    return {"true_sigma": sigma, "modulation": b, "exposure": exposure, "shape": shape}


def run(
    capture_dir: Path,
    out_dir: Path,
    n_periods: float = 8.0,
    surface: str | None = None,
    injected_sigma: float | None = None,
    modulation_threshold: float = 0.03,
    erode_px: int = 10,
    verbose: bool = True,
) -> dict:
    """Estimate the noise in a capture stack and turn it into a height error
    margin. When `injected_sigma` (normalized) is given, the estimate is scored
    against it. Writes a height-uncertainty map (um) and a per-pixel noise map
    (DN) to out_dir; returns a metrics dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = reconstruct.load_frames(capture_dir)
    n, h_px, w_px = frames.shape

    sigma_map = fit_residual_sigma(frames)
    phase, modulation = reconstruct.extract_phase(frames)

    valid = modulation > modulation_threshold
    if erode_px > 0:
        valid = cv2.erode(valid.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=erode_px).astype(bool)
    # Clipped samples aren't Gaussian noise and corrupt the residual fit.
    saturated = np.any(frames >= 254.5 / 255.0, axis=0)
    black = np.any(frames <= 0.5 / 255.0, axis=0)
    clipped = saturated | black
    est_mask = valid & ~clipped

    if est_mask.any():
        sigma_norm = float(np.sqrt(np.mean(sigma_map[est_mask] ** 2)))
    else:
        sigma_norm = float("nan")
    sigma_spatial = float(np.mean([immerkaer_sigma(f) for f in frames]))

    # Propagate to a per-pixel height uncertainty (mm).
    lambda_eq = reconstruct.equivalent_wavelength_mm(n_periods, THETA_DEG)
    b = np.clip(modulation, 1e-6, None)
    sigma_h = (lambda_eq / (2.0 * np.pi)) * sigma_norm * math.sqrt(2.0 / n) / b  # mm
    sh_valid = sigma_h[valid]
    mean_um = float(np.mean(sh_valid) * 1000.0)
    median_um = float(np.median(sh_valid) * 1000.0)
    p95_um = float(np.percentile(sh_valid, 95) * 1000.0)
    predicted_rmse_mm = float(np.sqrt(np.mean(sh_valid ** 2)))

    metrics = {
        "surface": surface,
        "frames": n,
        "valid_pixels": int(valid.sum()),
        "total_pixels": int(valid.size),
        "sigma_est_dn": sigma_norm * 255.0,
        "sigma_spatial_dn": sigma_spatial * 255.0,
        "lambda_eq_mm": lambda_eq,
        "height_uncertainty_um_mean": mean_um,
        "height_uncertainty_um_median": median_um,
        "height_uncertainty_um_p95": p95_um,
        "predicted_rmse_mm": predicted_rmse_mm,
        "saturated_frac": float(saturated.mean()),
    }
    if injected_sigma is not None:
        effective = math.hypot(injected_sigma, QUANT_SIGMA)  # + 8-bit quantization floor
        metrics["injected_sigma_dn"] = injected_sigma * 255.0
        metrics["sigma_rel_error"] = float(sigma_norm / effective - 1.0) if effective > 0 else float("nan")

    if verbose:
        line = f"sigma_est = {metrics['sigma_est_dn']:.2f} DN (spatial {metrics['sigma_spatial_dn']:.2f} DN)"
        if injected_sigma is not None:
            line += f", injected {metrics['injected_sigma_dn']:.2f} DN, rel.err {100 * metrics['sigma_rel_error']:+.1f}%"
        print(line)
        print(f"height uncertainty: mean {mean_um:.1f} um, p95 {p95_um:.1f} um (predicted RMSE {predicted_rmse_mm * 1000:.1f} um)")

    # Height-uncertainty map (um), clipped at p95 so a few weak-modulation
    # pixels don't wash out the scale.
    vmax = max(p95_um, 1e-6)
    sh_um = np.where(valid, sigma_h * 1000.0, np.nan)
    cv2.imwrite(str(out_dir / "noise_uncertainty.png"),
                reconstruct.colorize(np.nan_to_num(sh_um, nan=0.0), 0.0, vmax))
    # Per-pixel noise map (DN).
    noise_dn = np.where(valid, sigma_map * 255.0, np.nan)
    nmax = max(float(np.nanpercentile(noise_dn, 99)) if valid.any() else 1.0, 1e-6)
    cv2.imwrite(str(out_dir / "noise_map.png"),
                reconstruct.colorize(np.nan_to_num(noise_dn, nan=0.0), 0.0, nmax))

    with open(out_dir / "noise_metrics.txt", "w") as f:
        for key, value in metrics.items():
            f.write(f"{key}: {value}\n")
    return metrics


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-dir", default="out/capture", type=Path)
    parser.add_argument("--out-dir", default="out/noise", type=Path)
    parser.add_argument("--n-periods", default=8.0, type=float)
    parser.add_argument("--surface", default=None, choices=sorted(surfaces.SURFACES))
    parser.add_argument("--injected-sigma-dn", default=None, type=float,
                        help="known injected noise in DN, for scoring the estimate")
    parser.add_argument("--modulation-threshold", default=0.03, type=float)
    parser.add_argument("--erode-px", default=10, type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    injected = args.injected_sigma_dn / 255.0 if args.injected_sigma_dn is not None else None
    run(
        args.capture_dir,
        args.out_dir,
        n_periods=args.n_periods,
        surface=args.surface,
        injected_sigma=injected,
        modulation_threshold=args.modulation_threshold,
        erode_px=args.erode_px,
    )


if __name__ == "__main__":
    main()
