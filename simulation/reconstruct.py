"""Phase extraction, height reconstruction, and ground-truth comparison.

Loads the N-step phase-shifted capture stack (capture_pipeline.py), extracts
phase via the N-step PSA (report/math.tex, "N-step phase-shifting
algorithm"), converts phase to height via this rig's phase-to-height
relation (report/math.tex, "Height from phase, for this rig's geometry"),
and compares the result against the known ground-truth bump (surfaces.py).

Pure numpy/opencv on the rendered PNG frames -- no bpy/Blender needed here:
    .venv/bin/python3 simulation/reconstruct.py \
        --capture-dir out/capture --out-dir out/reconstruction --n-periods 8
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np

import surfaces
from geometry_constants import (
    CAM_PIXELS,
    D_PROJ_MM,
    H0_MM,
    THETA_DEG,
    W0_MM,
    W_PROJ_MM,
)


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


def reconstruct_height(psi: np.ndarray, n_periods: float, theta_deg: float) -> float:
    """Returns lambda_eq (mm); h = psi/(2*pi) * lambda_eq (report/math.tex
    Eq. height-from-phase)."""
    p_eff = W_PROJ_MM / n_periods
    lambda_eq = p_eff / math.tan(math.radians(theta_deg))
    return lambda_eq


def colorize(value: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
    norm = np.clip((value - vmin) / (vmax - vmin), 0.0, 1.0)
    gray = (norm * 255).astype(np.uint8)
    return cv2.applyColorMap(gray, cv2.COLORMAP_TURBO)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-dir", default="out/capture", type=Path)
    parser.add_argument("--out-dir", default="out/reconstruction", type=Path)
    parser.add_argument("--n-periods", default=8.0, type=float)
    parser.add_argument("--modulation-threshold", default=0.03, type=float)
    parser.add_argument("--erode-px", default=10, type=int, help="shrink the valid mask inward by this many pixels, away from field boundaries")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    frames = load_frames(args.capture_dir)
    n, h_px, w_px = frames.shape
    print(f"loaded {n} frames of shape {h_px}x{w_px}")

    phase, modulation = extract_phase(frames)
    valid = modulation > args.modulation_threshold
    if args.erode_px > 0:
        valid = cv2.erode(valid.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=args.erode_px).astype(bool)
    print(f"valid (masked) pixels: {valid.sum()} / {valid.size} ({100 * valid.mean():.1f}%)")

    world_x, world_y = pixel_to_world((h_px, w_px), THETA_DEG)
    phi_carrier = carrier_phase(world_x, args.n_periods)
    psi = wrap_to_pi(phase - phi_carrier)

    lambda_eq = reconstruct_height(psi, args.n_periods, THETA_DEG)
    height = psi / (2.0 * np.pi) * lambda_eq

    ground_truth = surfaces.bump_height_mm(world_x, world_y)

    error = height - ground_truth
    err_valid = error[valid]
    rmse = float(np.sqrt(np.mean(err_valid ** 2)))
    mae = float(np.mean(np.abs(err_valid)))
    max_abs = float(np.max(np.abs(err_valid)))
    r2 = 1.0 - np.sum(err_valid ** 2) / np.sum((ground_truth[valid] - ground_truth[valid].mean()) ** 2)

    print(f"lambda_eq = {lambda_eq:.3f} mm")
    print(f"RMSE = {rmse:.4f} mm, MAE = {mae:.4f} mm, max|err| = {max_abs:.4f} mm, R^2 = {r2:.4f}")

    vmin, vmax = float(ground_truth[valid].min()), float(ground_truth[valid].max())
    height_masked = np.where(valid, height, np.nan)
    cv2.imwrite(str(args.out_dir / "height_reconstructed.png"), colorize(np.nan_to_num(height_masked, nan=vmin), vmin, vmax))
    cv2.imwrite(str(args.out_dir / "height_ground_truth.png"), colorize(np.where(valid, ground_truth, vmin), vmin, vmax))
    err_abs_max = float(np.abs(err_valid).max())
    err_masked = np.where(valid, error, 0.0)
    cv2.imwrite(str(args.out_dir / "height_error.png"), colorize(err_masked, -err_abs_max, err_abs_max))

    with open(args.out_dir / "metrics.txt", "w") as f:
        f.write(f"frames: {n}\n")
        f.write(f"valid_pixels: {int(valid.sum())} / {valid.size}\n")
        f.write(f"lambda_eq_mm: {lambda_eq:.4f}\n")
        f.write(f"RMSE_mm: {rmse:.4f}\n")
        f.write(f"MAE_mm: {mae:.4f}\n")
        f.write(f"max_abs_err_mm: {max_abs:.4f}\n")
        f.write(f"R2: {r2:.4f}\n")

    print(f"wrote outputs to {args.out_dir}")


if __name__ == "__main__":
    main()
