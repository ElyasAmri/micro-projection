"""Slope and self-shadow/self-occlusion analysis for the test surfaces.

Quantifies, per surface and before any render is spent, how much of the
field the rig cannot measure: the per-pixel slope map, and the fraction of
pixels hidden from each device by the terrain itself (a directional
horizon scan -- a point is shadowed when terrain between it and the device
rises above the ray to it).

Budgets come from this rig's real geometry (geometry_constants):

* Camera: tilted THETA_DEG from normal, viewing from the +x side (rig.py
  add_telecentric_camera), so its rays arrive at elevation 90 - THETA_DEG
  ~= 51.3 degrees from the +x azimuth. Any surface slope facing away
  steeper than that hides its far side from the camera (self-occlusion of
  the view).
* Projector: on-axis rays are vertical (normal incidence -- no shadow from
  any single-valued surface), but it is a point source at D_PROJ_MM, so at
  the footprint's x-edges rays tilt by atan((W_PROJ_MM/2)/D_PROJ_MM) ~=
  19.6 degrees. The reported projector figure scans at that WORST-CASE
  edge elevation (~70.4 degrees) from each side and takes the mean --
  conservative: interior points see steeper rays than assumed.

Ported/adapted from the pre-rewrite sim's verify_surface_occlusion.py; that
rig had both devices at 41.4 degrees (a 48.6 degree budget), so its numbers
do not transfer -- these are recomputed for this geometry.

Run:
    .venv/bin/python3 simulation/occlusion.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import surfaces  # noqa: E402
from geometry_constants import D_PROJ_MM, H0_MM, THETA_DEG, W_PROJ_MM  # noqa: E402

CAMERA_ELEVATION_DEG = 90.0 - THETA_DEG
PROJECTOR_EDGE_ELEVATION_DEG = 90.0 - math.degrees(
    math.atan((W_PROJ_MM / 2.0) / D_PROJ_MM))


def field_grid(nx: int = 500, ny: int = 380):
    """(x, y) mm meshgrids over the projected footprint."""
    xs = np.linspace(-W_PROJ_MM / 2.0, W_PROJ_MM / 2.0, nx)
    ys = np.linspace(-H0_MM / 2.0, H0_MM / 2.0, ny)
    return np.meshgrid(xs, ys)


def slope_deg(z_mm: np.ndarray, pitch_x_mm: float,
              pitch_y_mm: float) -> np.ndarray:
    """Per-pixel surface slope angle (degrees) from the height gradient."""
    gy, gx = np.gradient(z_mm, pitch_y_mm, pitch_x_mm)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def shadow_fraction(z_mm: np.ndarray, pitch_mm: float, elevation_deg: float,
                    azimuth: str = "+x") -> float:
    """Fraction of the field hidden from rays arriving at `elevation_deg`
    from `azimuth` (one of +x/-x/+y/-y). Directional horizon scan: walking
    away from the device, the running horizon drops by tan(elevation) per
    step; a sample below it is shadowed."""
    # x ascends with column and y with row (field_grid), so rays from +x
    # already arrive from the last column; the other azimuths reorient to
    # match that canonical case.
    flips = {"+x": lambda a: a, "-x": lambda a: a[:, ::-1],
             "+y": lambda a: a.T, "-y": lambda a: a.T[:, ::-1]}
    if azimuth not in flips:
        raise ValueError(f"azimuth must be one of {sorted(flips)}")
    # Reorient so rays arrive from the LAST column; scan left-to-right.
    z = flips[azimuth](np.asarray(z_mm, dtype=float))
    drop = math.tan(math.radians(elevation_deg)) * pitch_mm
    shadow = np.zeros(z.shape, dtype=bool)
    horizon = z[:, -1].copy()
    for c in range(z.shape[1] - 2, -1, -1):
        horizon = np.maximum(horizon - drop, z[:, c])
        shadow[:, c] = horizon > z[:, c] + 1e-9
    return float(shadow.mean())


def analyze(height_fn, nx: int = 500, ny: int = 380) -> dict:
    """Slope and shadow metrics for one surface over the footprint."""
    x, y = field_grid(nx, ny)
    z = np.asarray(height_fn(x, y), dtype=float)
    px = W_PROJ_MM / (nx - 1)
    py = H0_MM / (ny - 1)
    ang = slope_deg(z, px, py)
    cam = shadow_fraction(z, px, CAMERA_ELEVATION_DEG, azimuth="+x")
    proj = np.mean([
        shadow_fraction(z, px, PROJECTOR_EDGE_ELEVATION_DEG, azimuth="+x"),
        shadow_fraction(z, px, PROJECTOR_EDGE_ELEVATION_DEG, azimuth="-x"),
    ])
    return {
        "max_slope_deg": float(ang.max()),
        "p99_slope_deg": float(np.percentile(ang, 99)),
        "camera_hidden_pct": 100.0 * cam,
        "projector_shadow_pct": 100.0 * float(proj),
        "relief_mm": float(z.max() - z.min()),
    }


def main() -> None:
    print(f"camera budget: elevation {CAMERA_ELEVATION_DEG:.1f} deg from +x "
          f"(theta {THETA_DEG} deg); projector worst-case edge elevation "
          f"{PROJECTOR_EDGE_ELEVATION_DEG:.1f} deg")
    header = (f"{'surface':<14} {'max_slope':>9} {'p99':>6} "
              f"{'cam_hidden':>10} {'proj_shadow':>11} {'relief':>7}")
    print(header)
    for name, fn in surfaces.SURFACES.items():
        m = analyze(fn)
        print(f"{name:<14} {m['max_slope_deg']:8.1f}d {m['p99_slope_deg']:5.1f}d "
              f"{m['camera_hidden_pct']:9.2f}% {m['projector_shadow_pct']:10.2f}% "
              f"{m['relief_mm']:6.2f}mm")


if __name__ == "__main__":
    main()
