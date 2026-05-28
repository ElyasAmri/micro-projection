"""Areal surface-roughness validation on the rolling-mound-rough surface.

Reuses the verify pipeline's reconstruction, then applies a Gaussian S-filter
(ISO 16610-21) to separate form from roughness, computes Sa, Sz (ISO 25178) on
the roughness residual, and validates against the analytic ground truth:

  A. analytic Sa, Sz   - from the surface formula's roughness component, sampled
                         densely over the patch (the true roughness of the part).
  B. filter-on-truth   - apply the Gaussian filter to the rendered ground-truth
                         height; Sa, Sz on its residual. Isolates filter accuracy
                         from reconstruction noise.
  C. filter-on-recon   - the measured value: apply the same filter to the
                         reconstructed height; Sa, Sz on its residual.

If C is close to B, the system reproduces what the filter would extract from
ideal data. If B is close to A, the filter cutoff is well-chosen.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "simulation"))
from outputs import load_ground_truth, load_sequence, period_label
from geometry import fringe_pitch_mm
from solver import direct_photometric_depth_solve
from reconstruction import phase_shift_sequence, robust_modulation_mask, similarity_metrics
from reconstruction import (
    gaussian_form_filter,
    sa_roughness,
    sigma_pixels_for_cutoff,
    sz_roughness,
)

PERIODS = [48.0, 192.0, 768.0]
DEFAULT_CUTOFF_MM = 15.0     # form vs roughness separation cutoff (lambda_c)
ERODE_PX = 20                 # exclude low-modulation field-boundary band


def _rough_component_mm(x_norm: np.ndarray, y_norm: np.ndarray) -> np.ndarray:
    """The analytic high-frequency component of `rolling-mound-rough`, in mm.

    Mirrors shared/synthetic_surfaces.py exactly. Returned in mm to match
    reconstruction units throughout this script.
    """
    rough_cm = (
        0.018 * np.sin(7.0 * np.pi * x_norm) * np.sin(5.0 * np.pi * y_norm)
        + 0.012 * np.sin(11.0 * np.pi * (x_norm + 0.13)) * np.cos(9.0 * np.pi * y_norm)
        + 0.008 * np.cos(13.0 * np.pi * x_norm - 0.4) * np.sin(7.5 * np.pi * (y_norm - 0.2))
    )
    return rough_cm * 10.0  # cm -> mm


def _recompute(base: Path):
    period_dirs = [base / f"period_{period_label(p)}" for p in PERIODS]
    metadata = json.loads((period_dirs[0] / "metadata.json").read_text())
    truth, valid_mask, object_mask = load_ground_truth(period_dirs[0])
    phases_deg = np.asarray(metadata["phases_deg"], dtype=np.float64)
    object_frames_list = [load_sequence(d / "object", "object") for d in period_dirs]
    reference_frames_list = [load_sequence(d / "reference", "reference") for d in period_dirs]
    object_seqs = [phase_shift_sequence(f) for f in object_frames_list]
    reference_seqs = [phase_shift_sequence(f) for f in reference_frames_list]
    modulation_mask = robust_modulation_mask(
        *[s.modulation for s in object_seqs],
        *[s.modulation for s in reference_seqs],
    )
    valid_object_mask = object_mask & valid_mask & modulation_mask
    reconstructed, _ = direct_photometric_depth_solve(
        metadata,
        valid_object_mask,
        object_frames_list,
        [np.deg2rad(phases_deg) for _ in object_frames_list],
        list(PERIODS),
        reference_sequences=None,
        reference_projector_x=None,
        coarse_candidate_count=3,
        quadratic_subsample=1,
    )
    solved_mask = valid_object_mask & np.isfinite(reconstructed)
    return truth, reconstructed, solved_mask, metadata


def _analytic_sa_sz(patch_width: float, patch_height: float, ngrid: tuple[int, int] = (2000, 1500)) -> tuple[float, float]:
    """Analytic roughness Sa, Sz (mm) of rolling-mound-rough over the full patch."""
    nu, nv = ngrid
    us = np.linspace(-patch_width / 2, patch_width / 2, nu)
    vs = np.linspace(-patch_height / 2, patch_height / 2, nv)
    U, Vv = np.meshgrid(us, vs)
    x_norm = U / (patch_width * 0.5)
    y_norm = Vv / (patch_height * 0.5)
    rough_mm = _rough_component_mm(x_norm, y_norm)
    return float(np.mean(np.abs(rough_mm))), float(rough_mm.max() - rough_mm.min())


def _crop_bbox(mask: np.ndarray, pad: int = 8):
    ys, xs = np.where(mask)
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad + 1, mask.shape[0])
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad + 1, mask.shape[1])
    return slice(y0, y1), slice(x0, x1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path,
                        default=REPO_ROOT / "out" / "blender_reconstruction_rolling-mound-rough")
    parser.add_argument("--out", type=Path,
                        default=REPO_ROOT / "out" / "roughness_rolling-mound-rough.png")
    parser.add_argument("--cutoff-mm", type=float, default=DEFAULT_CUTOFF_MM,
                        help="Gaussian S-filter cutoff wavelength (mm).")
    parser.add_argument("--erode-px", type=int, default=ERODE_PX)
    args = parser.parse_args()

    truth, recon, full_mask, metadata = _recompute(args.recording)
    print(f"recording: {args.recording}")
    print(f"surface:   {metadata.get('foreground_surface_kind')}")

    # Erode the mask to skip low-modulation field-boundary band, AND further by the
    # filter's effective radius so the filter has full support everywhere we measure.
    kernel_e = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * args.erode_px + 1,) * 2)
    eroded = cv2.erode(full_mask.astype(np.uint8), kernel_e).astype(bool)

    # Pixel pitch on the plane (mm/px) from the camera ortho_scale and render width.
    ortho_mm = float(metadata["capture_camera_ortho_scale"]) * 1000.0
    mm_per_px = ortho_mm / float(metadata["render_width"])
    sigma_pix = sigma_pixels_for_cutoff(args.cutoff_mm, mm_per_px)
    print(f"cutoff lambda_c = {args.cutoff_mm:.1f} mm   sigma = {sigma_pix:.2f} px   "
          f"({mm_per_px*1000:.1f} um/px)")

    # Form/roughness separation, in METRES (height units), applied to truth and recon.
    truth_form = gaussian_form_filter(truth, full_mask, sigma_pix)
    recon_form = gaussian_form_filter(recon, full_mask, sigma_pix)
    # Restrict residual to the eroded mask so the filter has full support.
    truth_rough = np.where(eroded, truth - truth_form, 0.0)
    recon_rough = np.where(eroded, recon - recon_form, 0.0)

    # Convert to mm.
    truth_rough_mm = truth_rough * 1000.0
    recon_rough_mm = recon_rough * 1000.0

    # Three Sa, Sz comparisons.
    sa_analytic, sz_analytic = _analytic_sa_sz(
        float(metadata["foreground_patch_width_m"]),
        float(metadata["foreground_patch_height_m"]),
    )
    sa_truth = sa_roughness(truth_rough_mm, eroded)
    sz_truth = sz_roughness(truth_rough_mm, eroded)
    sa_recon = sa_roughness(recon_rough_mm, eroded)
    sz_recon = sz_roughness(recon_rough_mm, eroded)

    print(f"Sa (analytic, full patch)     = {sa_analytic*1000:7.1f} um   Sz = {sz_analytic*1000:6.1f} um")
    print(f"Sa (filter on truth height)   = {sa_truth*1000:7.1f} um   Sz = {sz_truth*1000:6.1f} um")
    print(f"Sa (filter on reconstruction) = {sa_recon*1000:7.1f} um   Sz = {sz_recon*1000:6.1f} um")
    if sa_truth > 0:
        print(f"recon Sa / truth Sa = {sa_recon / sa_truth:.3f}")

    # ----- figure -----
    sy, sx = _crop_bbox(eroded)
    m = eroded[sy, sx]
    H_total = np.where(m, recon[sy, sx] * 1000.0, np.nan)
    H_form = np.where(m, recon_form[sy, sx] * 1000.0, np.nan)
    R_recon = np.where(m, recon_rough_mm[sy, sx] * 1000.0, np.nan)  # in micrometers
    R_truth = np.where(m, truth_rough_mm[sy, sx] * 1000.0, np.nan)

    h_lo, h_hi = float(np.nanmin([H_total, H_form])), float(np.nanmax([H_total, H_form]))
    r_lim = float(np.nanpercentile(np.abs(R_truth), 99.5))

    for cmap in ("viridis", "RdBu_r"):
        plt.get_cmap(cmap).set_bad((0.06, 0.07, 0.09, 1.0))

    bg = "#0d1117"
    fig, axes = plt.subplots(1, 4, figsize=(20, 5.6), facecolor=bg)
    panels = [
        ("Reconstructed height\n(form + roughness)", H_total, "viridis", h_lo, h_hi, "height (mm)"),
        (f"Separated form\n(Gaussian S-filter, lambda_c={args.cutoff_mm:.0f} mm)", H_form, "viridis", h_lo, h_hi, "height (mm)"),
        (f"Reconstructed roughness\nSa = {sa_recon*1000:.0f} um, Sz = {sz_recon*1000:.0f} um", R_recon, "RdBu_r", -r_lim, r_lim, "roughness (um)"),
        (f"Truth roughness\nSa = {sa_truth*1000:.0f} um, Sz = {sz_truth*1000:.0f} um", R_truth, "RdBu_r", -r_lim, r_lim, "roughness (um)"),
    ]
    for ax, (title, data, cmap, lo, hi, clabel) in zip(axes, panels):
        im = ax.imshow(data, cmap=cmap, vmin=lo, vmax=hi, interpolation="nearest")
        ax.set_title(title, color="#e6eaf2", fontsize=12.5, pad=10)
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color("#2d3442")
        cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cb.set_label(clabel, color="#aab2c0", fontsize=10)
        cb.ax.tick_params(colors="#aab2c0", labelsize=9)
        cb.outline.set_edgecolor("#2d3442")

    fig.suptitle(
        f"Roughness measurement on rolling-mound-rough   -   "
        f"analytic Sa {sa_analytic*1000:.0f} um  |  recon Sa {sa_recon*1000:.0f} um   "
        f"(recon/truth = {sa_recon/max(sa_truth,1e-12):.2f})",
        color="#e6eaf2", fontsize=15, y=0.99,
    )
    fig.subplots_adjust(left=0.02, right=0.99, top=0.86, bottom=0.04, wspace=0.22)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=140, facecolor=bg)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
