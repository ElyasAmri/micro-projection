"""Per-pixel phase-to-height calibration from known-z reference planes.

The nominal reconstruction (reconstruct.py) trusts the *design* geometry: an
analytic carrier phase (carrier_phase) and one equivalent wavelength
(equivalent_wavelength_mm) for the whole field. On a real rig those are only
approximate -- the projector's perspective, the camera pose, and lens distortion
make the true phase-to-height relation vary across the field, which prints as the
off-center bias and the ~0.5mm form error the Blender camera captures show
(report/math.tex "Roughness under a real camera", "Validation battery").

Calibration replaces the analytic model with a MEASURED one. Image a flat plane
at several known heights z (a z-stage; in simulation, capture_pipeline's
--z-offset) and, at every pixel, fit the surface phase psi (relative to the
analytic carrier, reconstruct.psi_from_frames) linearly in z:

    psi(p, z) = c0(p) + k(p) * z

  * c0(p) is the residual carrier error at that pixel -- what the analytic
    reference gets wrong (0 if it were perfect). Subtracting it is per-pixel
    reference-plane correction.
  * k(p) = dpsi/dz is the local phase sensitivity, = 2*pi / lambda_eq(p),
    absorbing the perspective's spatial variation (a per-pixel lambda_eq in
    place of one constant).

Reconstruction then inverts it per pixel, from the ladder-unwrapped fine phase:

    z(p) = (psi_fine_unwrapped(p) - c0(p)) / k(p)

This is the standard fringe-projection height calibration (cf. the Chapter 4
paper's lambda_eq calibration against a VLSI step height -- done here per pixel,
from a small z sweep). It corrects the height *scale* and the smooth off-center
bias; it does NOT remap pixels laterally (a lateral pixel->world calibration
against a known target is a separate step).

    .venv/bin/python3 simulation/calibration.py \
        --plane-dirs out/cal/z-0.5 out/cal/z0 out/cal/z0.5 \
        --z-values -0.5 0.0 0.5 --n-periods 80 --out out/cal/calib.npz
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

import reconstruct
from geometry_constants import THETA_DEG


class Calibration:
    """A measured geometry: the per-pixel phase-to-height map z = (psi - c0) / k
    (vertical), and optionally a pixel->world affine (lateral). `n_periods` is the
    rung the vertical calibration was measured at (the finest, which sets height).

    `lateral` is a 2x3 affine [x; y] = A [col; row; 1] mapping camera pixel to
    world (x, y) mm on the reference plane, or None to fall back to the nominal
    analytic map (reconstruct.pixel_to_world)."""

    def __init__(self, c0: np.ndarray, k: np.ndarray, valid: np.ndarray,
                 n_periods: float, z_values: np.ndarray, fit_rms_um: float,
                 lateral: np.ndarray | None = None, lateral_rms_um: float = float("nan")):
        self.c0 = c0
        self.k = k
        self.valid = valid
        self.n_periods = float(n_periods)
        self.z_values = np.asarray(z_values)
        self.fit_rms_um = float(fit_rms_um)
        self.lateral = None if lateral is None else np.asarray(lateral, dtype=np.float64)
        self.lateral_rms_um = float(lateral_rms_um)

    def save(self, path: Path) -> None:
        np.savez(path, c0=self.c0, k=self.k, valid=self.valid, n_periods=self.n_periods,
                 z_values=self.z_values, fit_rms_um=self.fit_rms_um,
                 has_lateral=(self.lateral is not None),
                 lateral=(self.lateral if self.lateral is not None else np.zeros((2, 3))),
                 lateral_rms_um=self.lateral_rms_um)

    @classmethod
    def load(cls, path: Path) -> "Calibration":
        d = np.load(path)
        lateral = d["lateral"] if bool(d["has_lateral"]) else None
        return cls(d["c0"], d["k"], d["valid"], float(d["n_periods"]), d["z_values"],
                   float(d["fit_rms_um"]), lateral, float(d["lateral_rms_um"]))

    def height_from_unwrapped_psi(self, psi_fine_unwrapped: np.ndarray) -> np.ndarray:
        """Calibrated height (mm) from the ladder-unwrapped fine-rung phase."""
        k = np.where(np.abs(self.k) > 1e-9, self.k, np.nan)
        return (psi_fine_unwrapped - self.c0) / k

    def world_grid(self, shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
        """Per-pixel world (x, y) mm: the calibrated affine if a lateral map was
        measured, else the nominal analytic map (reconstruct.pixel_to_world)."""
        if self.lateral is None:
            return reconstruct.pixel_to_world(shape, THETA_DEG)
        h, w = shape
        cols, rows = np.meshgrid(np.arange(w), np.arange(h))
        a = self.lateral
        world_x = a[0, 0] * cols + a[0, 1] * rows + a[0, 2]
        world_y = a[1, 0] * cols + a[1, 1] * rows + a[1, 2]
        return world_x, world_y


def calibrate(
    z_values_mm: list[float],
    plane_capture_dirs: list[Path],
    n_periods: float = 80.0,
    modulation_threshold: float = 0.03,
    erode_px: int = 10,
) -> Calibration:
    """Fit the per-pixel phase-to-height map from flat planes at known heights.

    Each `plane_capture_dirs[i]` is an N-step stack of a flat plane at
    `z_values_mm[i]`, captured at the finest rung `n_periods`. Returns a
    Calibration. The per-plane surface phase is unwrapped across z before the
    linear fit (the z steps are small, < half a fringe, so this is unambiguous)."""
    if len(z_values_mm) != len(plane_capture_dirs):
        raise ValueError("z_values and plane_capture_dirs must match in length")
    if len(z_values_mm) < 2:
        raise ValueError("need >= 2 planes to fit a phase-to-height slope")

    z = np.asarray(z_values_mm, dtype=np.float64)
    order = np.argsort(z)  # unwrap across z needs monotonic z
    z = z[order]
    dirs = [Path(plane_capture_dirs[i]) for i in order]

    psi_stack = []
    valid = None
    world_x = None
    for cdir in dirs:
        frames = reconstruct.load_frames(cdir)
        if world_x is None:
            world_x, _ = reconstruct.pixel_to_world(frames.shape[1:], THETA_DEG)
        psi, modulation = reconstruct.psi_from_frames(frames, n_periods, world_x)
        m = reconstruct._valid_mask(modulation, modulation_threshold, erode_px)
        valid = m if valid is None else (valid & m)
        psi_stack.append(psi)
    psi_raw = np.stack(psi_stack, axis=0)  # (nz, H, W), wrapped

    # Unwrap the wrapped per-plane phase across z. np.unwrap along z is fragile
    # here: at high-sensitivity pixels the z sweep can span >1 fringe and, with
    # only a few planes, it mis-jumps by 2*pi (corrupting c0/k for ~the highest-k
    # tail). Instead snap each plane's phase to the nearest fringe of the expected
    # value k_guess*z -- robust as long as the sweep stays within +/-pi of that
    # guess (which the analytic carrier, verified ~0 at z=0, makes true).
    k_guess = 2.0 * np.pi / reconstruct.equivalent_wavelength_mm(n_periods, THETA_DEG)
    expected = k_guess * z[:, None, None]
    psi_stack = psi_raw + 2.0 * np.pi * np.round((expected - psi_raw) / (2.0 * np.pi))

    # Per-pixel least-squares line psi = c0 + k*z (closed form).
    zc = z - z.mean()
    denom = float(np.sum(zc * zc))
    psi_mean = psi_stack.mean(axis=0)
    k = np.tensordot(zc, psi_stack - psi_mean, axes=(0, 0)) / denom
    c0 = psi_mean - k * z.mean()

    # Fit residual, as a height, over the valid region -- a QA number.
    model = c0[None] + k[None] * z[:, None, None]
    resid = psi_stack - model
    k_safe = np.where(np.abs(k) > 1e-9, k, np.nan)
    resid_um = np.abs(resid / k_safe[None]) * 1000.0
    fit_rms_um = float(np.sqrt(np.nanmean((resid_um[:, valid]) ** 2))) if valid.any() else float("nan")

    return Calibration(c0, k, valid, n_periods, z, fit_rms_um)


def detect_dots(image: np.ndarray, min_area: int = 100, max_area: int = 6000) -> np.ndarray:
    """Centroids (col, row) of the dark dots in a rendered dot-grid target
    (rig.add_target_plane). Threshold at the mid-level, take dot-sized connected
    components, return their centroids -- sub-pixel enough that the affine fit
    averages out the residual. `image` is 8-bit grayscale."""
    import cv2
    thresh = (int(image.min()) + int(image.max())) / 2.0
    dark = (image < thresh).astype(np.uint8)
    n, _labels, stats, centroids = cv2.connectedComponentsWithStats(dark, connectivity=8)
    keep = [i for i in range(1, n) if min_area < stats[i, cv2.CC_STAT_AREA] < max_area]
    return centroids[keep]  # (N, 2) as (x=col, y=row)


def calibrate_lateral(
    centroids_px: np.ndarray, spacing_mm: float, shape: tuple[int, int]
) -> tuple[np.ndarray, float]:
    """Fit the pixel->world affine from detected dot centroids.

    The dots sit on a known `spacing_mm` world grid (rig.add_target_plane, centers
    at (i*s, j*s) mm). Map each centroid through the nominal analytic map to an
    approximate world position and snap it to the nearest grid node -- its exact
    known world coordinate (robust: the nominal error, ~0.5mm, is far under half a
    spacing). Then least-squares fit [x; y] = A [col; row; 1]. Returns (A 2x3,
    fit RMS in um)."""
    world_x_nom, world_y_nom = reconstruct.pixel_to_world(shape, THETA_DEG)
    cols, rows = centroids_px[:, 0], centroids_px[:, 1]
    ci = np.clip(np.round(cols).astype(int), 0, shape[1] - 1)
    ri = np.clip(np.round(rows).astype(int), 0, shape[0] - 1)
    wx_true = np.round(world_x_nom[ri, ci] / spacing_mm) * spacing_mm
    wy_true = np.round(world_y_nom[ri, ci] / spacing_mm) * spacing_mm

    m = np.column_stack([cols, rows, np.ones_like(cols)])
    ax, *_ = np.linalg.lstsq(m, wx_true, rcond=None)
    ay, *_ = np.linalg.lstsq(m, wy_true, rcond=None)
    a = np.vstack([ax, ay])  # 2x3
    resid_um = float(np.sqrt(np.mean((m @ ax - wx_true) ** 2 + (m @ ay - wy_true) ** 2)) * 1000.0)
    return a, resid_um


def add_lateral(calib: Calibration, target_image: np.ndarray, spacing_mm: float) -> Calibration:
    """Measure the lateral pixel->world map from a dot-grid target frame and
    attach it to `calib` (in place); returns it."""
    centroids = detect_dots(target_image)
    if len(centroids) < 3:
        raise ValueError(f"only {len(centroids)} dots detected; need >= 3 for an affine fit")
    calib.lateral, calib.lateral_rms_um = calibrate_lateral(centroids, spacing_mm, target_image.shape)
    return calib


def reconstruct_calibrated(
    ladder_capture_dirs: list[Path],
    out_dir: Path,
    calib: Calibration,
    n_periods_ladder: list[float] | None = None,
    surface: str | None = None,
    modulation_threshold: float = 0.03,
    erode_px: int = 10,
    normalize_gains: bool = True,
    parallax: bool = True,
    verbose: bool = True,
) -> dict:
    """Reconstruct a surface from its coarse->fine ladder, then convert the
    unwrapped fine-rung phase to height with `calib` instead of the analytic
    lambda_eq/carrier. The ladder still supplies the (robust, integer) fringe
    orders; calibration only corrects the final phase-to-height map.

    Lateral placement uses the calibrated pixel->world map (calib.world_grid);
    with `parallax`, each height is then shifted by h*tan(theta) along x -- the
    tilted telecentric camera images an elevated point offset in x, and without
    this the height lands at its z=0 position (the ~0.5mm mis-registration of
    report/math.tex). Scored and written like reconstruct.run_multifreq."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if n_periods_ladder is None:
        from geometry_constants import N_PERIODS_LADDER
        n_periods_ladder = list(N_PERIODS_LADDER)

    # Nominal ladder unwrap gives the fine-rung height; recover its unwrapped
    # phase (height * 2*pi / lambda_eq_fine) and re-map it through the calibration.
    nominal = reconstruct.run_multifreq(
        ladder_capture_dirs, out_dir / "_nominal", n_periods_ladder=n_periods_ladder,
        surface=None, modulation_threshold=modulation_threshold, erode_px=erode_px,
        normalize_gains=normalize_gains, verbose=False,
    )
    height_nominal = np.load(out_dir / "_nominal" / "height.npy")
    valid_nominal = np.load(out_dir / "_nominal" / "valid.npy")

    lambda_fine = reconstruct.equivalent_wavelength_mm(n_periods_ladder[-1], THETA_DEG)
    psi_fine_unwrapped = height_nominal * (2.0 * np.pi / lambda_fine)
    height = calib.height_from_unwrapped_psi(psi_fine_unwrapped)

    valid = valid_nominal & calib.valid & np.isfinite(height)
    height = np.nan_to_num(height, nan=0.0)
    # Placement (and thus ground-truth scoring) uses the calibrated world map, so
    # a corrected lateral registration actually shows up in the score.
    world_x, world_y = calib.world_grid(height.shape)
    if parallax:  # tilted camera: an elevated point images shifted by h*tan(theta) in x
        world_x = world_x + height * np.tan(np.radians(THETA_DEG))

    metrics = {
        "surface": surface,
        "calibrated": True,
        "n_periods_ladder": list(n_periods_ladder),
        "valid_pixels": int(valid.sum()),
        "total_pixels": int(valid.size),
        "lambda_eq_mm": lambda_fine,
        "calib_fit_rms_um": calib.fit_rms_um,
        "lateral_calibrated": calib.lateral is not None,
        "lateral_fit_rms_um": calib.lateral_rms_um,
        "parallax_corrected": parallax,
    }
    metrics = reconstruct._write_and_score(height, valid, world_x, world_y, out_dir, surface, metrics, verbose)
    if verbose:
        print(f"calibrated reconstruct: valid {100 * valid.mean():.1f}%, calib fit RMS {calib.fit_rms_um:.1f} um")
    return metrics


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--plane-dirs", nargs="+", type=Path, required=True,
                   help="flat-plane capture stacks, one per known z")
    p.add_argument("--z-values", nargs="+", type=float, required=True,
                   help="plane heights (mm) matching --plane-dirs")
    p.add_argument("--n-periods", type=float, default=80.0, help="rung the planes were captured at")
    p.add_argument("--out", type=Path, default=Path("out/cal/calib.npz"))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    calib = calibrate(args.z_values, args.plane_dirs, n_periods=args.n_periods)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    calib.save(args.out)
    print(f"calibrated from {len(args.z_values)} planes; fit RMS {calib.fit_rms_um:.2f} um; "
          f"k median {np.nanmedian(calib.k[calib.valid]):.3f} rad/mm "
          f"(nominal {2 * np.pi / reconstruct.equivalent_wavelength_mm(args.n_periods, THETA_DEG):.3f}); "
          f"wrote {args.out}")


if __name__ == "__main__":
    main()
