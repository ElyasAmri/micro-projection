"""Surface roughness from a reconstructed height map -- the end goal.

The multi-frequency ladder (reconstruct.run_multifreq) recovers a height map that
resolves a small, high-frequency *roughness* texture riding on a large, smooth
*form* (waviness). This module makes the last step: separate the two and report
the roughness as areal parameters (ISO 25178), with the noise floor the estimate
inherits from the camera.

Separation. An ISO-25178 Gaussian regression filter (ISO 16610-61) splits the
height by spatial wavelength: the *form* is the height smoothed with a Gaussian
of cutoff wavelength lambda_c (standard deviation sigma = 0.1874 * lambda_c);
the *roughness* is what's left, height - form. The blur is mask-aware
(normalized convolution) so invalid pixels at the field edge don't bleed a false
slope into the form. Everything coarser than lambda_c is called form, everything
finer roughness -- so lambda_c must sit between the two bands (the `rough`
specimen is built that way; see surfaces.py).

Parameters. On the form-removed residual, over the valid region and relative to
its mean plane: Sa (arithmetic mean height), Sq (RMS height), Sz (max
peak-to-valley), plus Sp/Sv/Ssk/Sku. Heights are reported in micrometres.

Noise floor. Per-pixel camera noise adds in quadrature to the RMS roughness:
Sq_meas^2 = Sq_true^2 + sigma_h^2, where sigma_h is the height uncertainty the
noise pipeline estimates on the finest rung (noise_estimate.run). So the module
reports a noise-corrected Sq and a roughness SNR = Sq / sigma_h -- if the SNR is
near 1 the "roughness" is mostly noise, which is exactly what you need to know.

    .venv/bin/python3 simulation/roughness.py \
        --capture-dirs out/app/rough/capture_f0 out/app/rough/capture_f1 \
                       out/app/rough/capture_f2 \
        --out-dir out/roughness --surface rough --cutoff-mm 10
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np

import noise_estimate
import reconstruct
import surfaces
from geometry_constants import N_PERIODS_LADDER, THETA_DEG

# ISO 16610-61 Gaussian filter: the cutoff wavelength lambda_c maps to a Gaussian
# of standard deviation sigma = lambda_c * sqrt(ln 2 / (2*pi^2)).
_ISO_SIGMA_PER_LAMBDA = math.sqrt(math.log(2.0) / (2.0 * math.pi ** 2))  # ~= 0.18739

# When the fine rung's temporal noise estimate exceeds its spatial (single-frame,
# white) estimate by more than this factor, the residual is dominated by
# *systematic* frame-to-frame error (projector gamma, phase-step error, a smooth
# Blender render artifact), not random noise -- flag it, because the random floor
# then does not bound the roughness map's fidelity.
SYSTEMATIC_RATIO_THRESH = 3.0


def gaussian_highpass(
    height: np.ndarray,
    valid: np.ndarray,
    dx_mm: float,
    dy_mm: float,
    cutoff_mm: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Split `height` into (roughness, form) at cutoff wavelength `cutoff_mm`.

    `form` is the ISO-25178 Gaussian regression mean; `roughness` is
    height - form. Mask-aware: the blur is a normalized convolution over `valid`,
    so the form doesn't dip toward zero at the field boundary. Both outputs are
    left unmasked (arrays over the full grid); callers restrict to `valid`."""
    sigma_x = _ISO_SIGMA_PER_LAMBDA * cutoff_mm / dx_mm  # px
    sigma_y = _ISO_SIGMA_PER_LAMBDA * cutoff_mm / dy_mm  # px
    w = valid.astype(np.float64)
    hv = np.where(valid, height, 0.0)
    # Normalized convolution: blurred(height*valid) / blurred(valid).
    num = cv2.GaussianBlur(hv, (0, 0), sigmaX=sigma_x, sigmaY=sigma_y, borderType=cv2.BORDER_REPLICATE)
    den = cv2.GaussianBlur(w, (0, 0), sigmaX=sigma_x, sigmaY=sigma_y, borderType=cv2.BORDER_REPLICATE)
    form = num / np.maximum(den, 1e-9)
    roughness = height - form
    return roughness, form


def areal_parameters(roughness: np.ndarray, valid: np.ndarray) -> dict:
    """ISO 25178 areal roughness on the form-removed residual, over `valid` and
    relative to its mean plane. Heights in micrometres."""
    r = roughness[valid]
    r = r - r.mean()  # S-parameters are defined about the mean plane
    absr = np.abs(r)
    sa = float(absr.mean())
    sq = float(np.sqrt(np.mean(r ** 2)))
    sp = float(r.max())
    sv = float(-r.min())
    ssk = float(np.mean(r ** 3) / sq ** 3) if sq > 0 else 0.0
    sku = float(np.mean(r ** 4) / sq ** 4) if sq > 0 else 0.0
    return {
        "Sa_um": sa * 1000.0,
        "Sq_um": sq * 1000.0,
        "Sz_um": (sp + sv) * 1000.0,
        "Sp_um": sp * 1000.0,
        "Sv_um": sv * 1000.0,
        "Ssk": ssk,
        "Sku": sku,
    }


def denoise_sq(sq_meas_um: float, sigma_h_um: float) -> tuple[float, float]:
    """Camera noise inflates the RMS roughness in quadrature
    (Sq_meas^2 = Sq_true^2 + sigma_h^2). Return (noise-corrected Sq, SNR)."""
    corrected = math.sqrt(max(sq_meas_um ** 2 - sigma_h_um ** 2, 0.0))
    snr = sq_meas_um / sigma_h_um if sigma_h_um > 0 else float("inf")
    return corrected, snr


def measure(
    height: np.ndarray,
    valid: np.ndarray,
    dx_mm: float,
    dy_mm: float,
    out_dir: Path,
    surface: str | None = None,
    cutoff_mm: float = 10.0,
    fine_capture_dir: Path | None = None,
    fine_n_periods: float | None = None,
    lambda_eq_fine_mm: float | None = None,
    verbose: bool = True,
) -> dict:
    """Roughness from an already-reconstructed height map: remove the form and
    report areal Sa/Sq/Sz. For a known specimen the identical filter is applied
    to the exact ground truth and the result is scored against it. If
    `fine_capture_dir` (the finest rung's stack) is given, its height
    uncertainty sets a noise floor -> a noise-corrected Sq and a roughness SNR.
    Writes a roughness map + metrics; returns the metrics dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    roughness, _form = gaussian_highpass(height, valid, dx_mm, dy_mm, cutoff_mm)
    params = areal_parameters(roughness, valid)

    metrics = {
        "surface": surface,
        "cutoff_mm": cutoff_mm,
        "valid_pixels": int(valid.sum()),
        "total_pixels": int(valid.size),
        **params,
    }
    if lambda_eq_fine_mm is not None:
        metrics["lambda_eq_fine_mm"] = lambda_eq_fine_mm

    # Score against ground truth: run the identical filter on the exact surface,
    # so any gap is the reconstruction's, not the form model's.
    if surface is not None and surface in surfaces.SURFACES:
        world_x, world_y = reconstruct.pixel_to_world(height.shape, THETA_DEG)
        gt_height = surfaces.SURFACES[surface](world_x, world_y)
        gt_rough, _ = gaussian_highpass(gt_height, valid, dx_mm, dy_mm, cutoff_mm)
        gt_params = areal_parameters(gt_rough, valid)
        metrics["Sa_true_um"] = gt_params["Sa_um"]
        metrics["Sq_true_um"] = gt_params["Sq_um"]
        metrics["Sa_err_um"] = params["Sa_um"] - gt_params["Sa_um"]
        metrics["Sq_err_um"] = params["Sq_um"] - gt_params["Sq_um"]

    if fine_capture_dir is not None:
        nm = noise_estimate.run(
            Path(fine_capture_dir), out_dir / "roughness_noise",
            n_periods=fine_n_periods, surface=None, verbose=False,
        )
        # The roughness floor is the RANDOM (white) noise that actually survives
        # the high-pass -- the single-frame spatial estimate. The temporal
        # residual also absorbs systematic frame-to-frame error, which form
        # filtering largely removes and which must not be counted as a random
        # floor. Scale the (per-pixel-modulation-weighted) temporal height
        # uncertainty down to the white level by the spatial/temporal ratio.
        temporal_dn = nm["sigma_est_dn"]
        spatial_dn = nm["sigma_spatial_dn"]
        scale = (spatial_dn / temporal_dn) if temporal_dn > 0 else 1.0
        white_floor_um = nm["height_uncertainty_um_median"] * scale
        sq_corr, snr = denoise_sq(params["Sq_um"], white_floor_um)
        metrics["noise_floor_um"] = white_floor_um
        metrics["Sq_denoised_um"] = sq_corr
        metrics["roughness_snr"] = snr  # random-noise SNR only
        metrics["systematic_ratio"] = (temporal_dn / spatial_dn) if spatial_dn > 0 else float("inf")
        metrics["systematic_error"] = metrics["systematic_ratio"] > SYSTEMATIC_RATIO_THRESH

    if verbose:
        line = (f"roughness {surface}: Sa={params['Sa_um']:.2f} um, "
                f"Sq={params['Sq_um']:.2f} um, Sz={params['Sz_um']:.2f} um")
        if "Sq_true_um" in metrics:
            line += f" (true Sq={metrics['Sq_true_um']:.2f} um, err {metrics['Sq_err_um']:+.2f} um)"
        print(line)
        if "roughness_snr" in metrics:
            print(f"random floor {metrics['noise_floor_um']:.2f} um -> "
                  f"Sq(denoised)={metrics['Sq_denoised_um']:.2f} um, random-SNR={metrics['roughness_snr']:.1f}")
            if metrics["systematic_error"]:
                print(f"  WARNING: systematic error present (temporal/spatial = "
                      f"{metrics['systematic_ratio']:.0f}x); the random floor does not bound map fidelity")

    # Roughness map, centered at 0 over +/-3*Sq so the texture, not a stray
    # outlier, sets the scale.
    span = max(3.0 * params["Sq_um"] / 1000.0, 1e-6)
    rough_masked = np.where(valid, roughness - np.mean(roughness[valid]), np.nan)
    cv2.imwrite(str(out_dir / "roughness_map.png"),
                reconstruct.colorize(np.nan_to_num(rough_masked, nan=0.0), -span, span))

    with open(out_dir / "roughness_metrics.txt", "w") as f:
        for key, value in metrics.items():
            f.write(f"{key}: {value}\n")
    return metrics


def run(
    capture_dirs: list[Path],
    out_dir: Path,
    surface: str | None = "rough",
    n_periods_ladder: list[float] | None = None,
    cutoff_mm: float = 10.0,
    estimate_noise: bool = True,
    verbose: bool = True,
) -> dict:
    """Measure roughness from a coarse->fine ladder of capture stacks: unwrap to a
    height map (reconstruct.run_multifreq), then measure() the form-removed
    roughness. The full CLI path; the app measures straight off an existing
    reconstruction via measure()."""
    if n_periods_ladder is None:
        n_periods_ladder = list(N_PERIODS_LADDER)
    out_dir.mkdir(parents=True, exist_ok=True)

    recon = reconstruct.run_multifreq(
        capture_dirs, out_dir, n_periods_ladder=n_periods_ladder, surface=surface, verbose=False
    )
    height = np.load(out_dir / "height.npy")
    valid = np.load(out_dir / "valid.npy")
    return measure(
        height, valid, recon["dx_mm"], recon["dy_mm"], out_dir,
        surface=surface, cutoff_mm=cutoff_mm,
        fine_capture_dir=(Path(capture_dirs[-1]) if estimate_noise else None),
        fine_n_periods=n_periods_ladder[-1],
        lambda_eq_fine_mm=recon["lambda_eq_mm"],
        verbose=verbose,
    )


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-dirs", nargs="+", type=Path, required=True,
                        help="coarse->fine per-frequency stacks (as produced by the multi-frequency pipeline)")
    parser.add_argument("--out-dir", default="out/roughness", type=Path)
    parser.add_argument("--surface", default="rough", choices=sorted(surfaces.SURFACES))
    parser.add_argument("--n-periods-ladder", nargs="+", type=float, default=None)
    parser.add_argument("--cutoff-mm", default=10.0, type=float,
                        help="form/roughness separation wavelength (ISO 25178 Gaussian filter)")
    parser.add_argument("--no-noise", action="store_true", help="skip the noise-floor estimate")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run(
        args.capture_dirs,
        args.out_dir,
        surface=args.surface,
        n_periods_ladder=args.n_periods_ladder,
        cutoff_mm=args.cutoff_mm,
        estimate_noise=not args.no_noise,
    )


if __name__ == "__main__":
    main()
