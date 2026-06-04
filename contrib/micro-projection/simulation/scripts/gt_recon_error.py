"""GT vs reconstruction figure: 3D height pair + signed and abs error heatmaps."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[2]
# verify_blender_reconstruction now lives at simulation/ root (after the PySide6
# removal flattened blendersim/ into simulation/).
sys.path.insert(0, str(REPO_ROOT / "simulation"))
from outputs import load_ground_truth, load_sequence, period_label
from geometry import fringe_pitch_mm
from solver import direct_photometric_depth_solve
from reconstruction import phase_shift_sequence, robust_modulation_mask, similarity_metrics

PERIODS = [48.0, 192.0, 768.0]  # solve order (matches reconstruction_metrics.json)
COARSE_CANDIDATES = 3
QUADRATIC_SUBSAMPLE = 1


def _recompute(base: Path):
    period_dirs = [base / f"period_{period_label(p)}" for p in PERIODS]
    metadata = json.loads((period_dirs[0] / "metadata.json").read_text())
    truth, valid_mask, object_mask = load_ground_truth(period_dirs[0])
    phases_deg = np.asarray(metadata["phases_deg"], dtype=np.float64)

    object_frames_list = [load_sequence(d / "object", "object") for d in period_dirs]
    reference_frames_list = [load_sequence(d / "reference", "reference") for d in period_dirs]
    object_sequences = [phase_shift_sequence(f) for f in object_frames_list]
    reference_sequences = [phase_shift_sequence(f) for f in reference_frames_list]
    modulation_mask = robust_modulation_mask(
        *[s.modulation for s in object_sequences],
        *[s.modulation for s in reference_sequences],
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
        coarse_candidate_count=COARSE_CANDIDATES,
        quadratic_subsample=QUADRATIC_SUBSAMPLE,
    )
    solved_mask = valid_object_mask & np.isfinite(reconstructed)
    metrics = similarity_metrics(reconstructed, truth, solved_mask)
    return truth, reconstructed, solved_mask, metrics, metadata


def _crop_bbox(mask, pad=12):
    ys, xs = np.where(mask)
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad + 1, mask.shape[0])
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad + 1, mask.shape[1])
    return slice(y0, y1), slice(x0, x1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path,
                        default=REPO_ROOT / "out" / "blender_reconstruction_rolling-mound",
                        help="Per-capture parent dir containing period_NNp0 subdirs.")
    parser.add_argument("--out", type=Path, default=None,
                        help="Output figure path. Default derives from surface_kind.")
    parser.add_argument("--erode-px", type=int, default=20,
                        help="Erode the solved-mask boundary by N pixels before computing "
                             "metrics and rendering, to exclude low-modulation edge artifacts "
                             "(standard practice). The README's reported metrics use 20. "
                             "0 disables.")
    args = parser.parse_args()

    truth, recon, mask, metrics_full, metadata = _recompute(args.recording)
    surface_kind = str(metadata.get("foreground_surface_kind", "surface"))
    out_path = args.out or (REPO_ROOT / "out" / f"gt_vs_reconstruction_{surface_kind}.png")
    print(f"recording: {args.recording}")
    print(f"surface:   {surface_kind}")
    print(f"metrics (full mask):     rmse={metrics_full.rmse:.6f} mae={metrics_full.mae:.6f} "
          f"max_abs={metrics_full.max_abs:.6f} r2={metrics_full.r2:.4f}")

    if args.erode_px > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * args.erode_px + 1, 2 * args.erode_px + 1))
        mask = cv2.erode(mask.astype(np.uint8), kernel).astype(bool)
        metrics = similarity_metrics(recon, truth, mask)
        print(f"metrics (eroded {args.erode_px}px): rmse={metrics.rmse:.6f} mae={metrics.mae:.6f} "
              f"max_abs={metrics.max_abs:.6f} r2={metrics.r2:.4f}")
    else:
        metrics = metrics_full

    sy, sx = _crop_bbox(mask)
    m = mask[sy, sx]
    t_mm = np.where(m, truth[sy, sx] * 1000.0, np.nan)
    r_mm = np.where(m, recon[sy, sx] * 1000.0, np.nan)
    err_mm = np.where(m, (truth[sy, sx] - recon[sy, sx]) * 1000.0, np.nan)  # gt - reconstruct
    abs_mm = np.abs(err_mm)

    h_lo, h_hi = float(np.nanmin([t_mm, r_mm])), float(np.nanmax([t_mm, r_mm]))
    e_max = float(np.nanpercentile(np.abs(err_mm), 99))
    a_max = float(np.nanpercentile(abs_mm, 99))

    for cmap in ("viridis", "RdBu_r", "inferno"):
        plt.get_cmap(cmap).set_bad((0.06, 0.07, 0.09, 1.0))

    # Physical extent of the cropped patch on the plane (mm), for true x/y scale.
    mm_per_px = float(metadata["capture_camera_ortho_scale"]) * 1000.0 / float(metadata["render_width"])
    step = 4  # decimate for a clean 3D surface
    Zt, Zr = t_mm[::step, ::step], r_mm[::step, ::step]
    rows, cols = Zt.shape
    xs = (np.arange(cols) - cols / 2.0) * step * mm_per_px
    ys = (np.arange(rows) - rows / 2.0) * step * mm_per_px
    XX, YY = np.meshgrid(xs, ys)
    x_span, y_span = float(np.ptp(xs)), float(np.ptp(ys))

    bg = "#0d1117"
    fig = plt.figure(figsize=(20, 5.6), facecolor=bg)
    norm = matplotlib.colors.Normalize(vmin=h_lo, vmax=h_hi)

    def add_surface(idx: int, Z: np.ndarray, title: str):
        ax = fig.add_subplot(1, 4, idx, projection="3d")
        ax.set_facecolor(bg)
        ax.plot_surface(XX, YY, Z, cmap="viridis", norm=norm, rstride=1, cstride=1,
                        linewidth=0, antialiased=True)
        ax.set_zlim(h_lo, h_hi)  # grounded: surface sits on the base plane
        ax.set_box_aspect((1.0, y_span / x_span, 0.45))
        ax.view_init(elev=58, azim=-90)  # top-front, not the camera's oblique angle
        ax.set_title(title, color="#e6eaf2", fontsize=14, pad=2)
        ax.set_xlabel("x (mm)", color="#aab2c0", fontsize=9, labelpad=-6)
        ax.set_ylabel("y (mm)", color="#aab2c0", fontsize=9, labelpad=-6)
        ax.tick_params(colors="#aab2c0", labelsize=7, pad=-2)
        ax.set_zticks([])
        for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
            axis.set_pane_color((0.06, 0.07, 0.09, 1.0))
            axis.pane.set_edgecolor((0.18, 0.20, 0.26, 1.0))
            axis._axinfo["grid"]["color"] = (0.18, 0.20, 0.26, 0.4)

    add_surface(1, Zt, "Ground truth")
    add_surface(2, Zr, "Reconstruction")
    sm = matplotlib.cm.ScalarMappable(norm=norm, cmap="viridis")
    cb = fig.colorbar(sm, ax=fig.axes[:2], fraction=0.02, pad=0.01, location="left")
    cb.set_label("height (mm)", color="#aab2c0", fontsize=10)
    cb.ax.tick_params(colors="#aab2c0", labelsize=9)
    cb.outline.set_edgecolor("#2d3442")

    def add_heat(idx: int, data, cmap, lo, hi, title, clabel):
        ax = fig.add_subplot(1, 4, idx)
        im = ax.imshow(data, cmap=cmap, vmin=lo, vmax=hi, interpolation="nearest")
        ax.set_title(title, color="#e6eaf2", fontsize=14, pad=10)
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color("#2d3442")
        cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cb.set_label(clabel, color="#aab2c0", fontsize=10)
        cb.ax.tick_params(colors="#aab2c0", labelsize=9)
        cb.outline.set_edgecolor("#2d3442")

    add_heat(3, err_mm, "RdBu_r", -e_max, e_max, "Error  (GT - reconstruction)", "signed error (mm)")
    add_heat(4, abs_mm, "inferno", 0.0, a_max, "Absolute error  |GT - recon|", "|error| (mm)")

    fig.suptitle(
        f"{surface_kind} reconstruction   -   RMSE {metrics.rmse*1000:.3f} mm   -   "
        f"MAE {metrics.mae*1000:.3f} mm   -   R2 {metrics.r2:.3f}",
        color="#e6eaf2", fontsize=16, y=0.99,
    )
    fig.subplots_adjust(left=0.04, right=0.99, top=0.90, bottom=0.04, wspace=0.22)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140, facecolor=bg)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
