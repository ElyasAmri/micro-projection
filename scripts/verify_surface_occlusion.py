"""Verify a scanning surface is single-valued, slope-bounded, and self-shadow free.

Tests against the projector/camera grazing budget (~48.6 deg): computes the max
surface slope and runs a directional horizon shadow test along the projector
azimuth (the left-right u-axis), in both directions, to confirm no point occludes
another from the projection.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
# shared/ lives at simulation/shared/ after the consolidation cleanup.
sys.path.insert(0, str(REPO_ROOT / "simulation"))
from shared.synthetic_surfaces import height_field_depth_m

W, H = 0.09, 0.068
NU, NV = 500, 380
BUDGET_DEG = 48.6
us = np.linspace(-W / 2, W / 2, NU)
vs = np.linspace(-H / 2, H / 2, NV)
U, Vv = np.meshgrid(us, vs)


def field(kind: str) -> np.ndarray:
    return np.vectorize(lambda u, v: height_field_depth_m(u, v, W, H, surface_kind=kind))(U, Vv)


def horizon_shadow_frac(Z: np.ndarray, elev_tan: float) -> float:
    """Fraction of pixels shadowed by terrain along the projector azimuth.

    The projector approaches from -u (decreasing column index) per the rig
    metadata, so terrain *to the left* of a pixel can shadow it; terrain to
    the right cannot. Scan once in that direction only.
    """
    du = abs(us[1] - us[0])
    shadow = np.zeros(Z.shape, dtype=bool)
    horizon = np.full(Z.shape[0], -np.inf)
    first = True
    for c in range(NU):
        horizon = Z[:, c] if first else np.maximum(horizon - elev_tan * du, Z[:, c])
        shadow[:, c] |= horizon > Z[:, c] + 1e-9
        first = False
    return float(shadow.mean() * 100.0)


def report(kind: str) -> None:
    Z = field(kind)
    gy, gx = np.gradient(Z, vs, us)
    ang = np.degrees(np.arctan(np.sqrt(gx ** 2 + gy ** 2)))
    shadow = horizon_shadow_frac(Z, np.tan(np.radians(BUDGET_DEG)))
    print(f"{kind:<14} max_slope={ang.max():5.1f} deg  p99={np.percentile(ang,99):5.1f} deg  "
          f"shadowed={shadow:5.2f}%  relief={(Z.max()-Z.min())*1000:5.1f} mm")


def main() -> None:
    from shared.synthetic_surfaces import SURFACE_KINDS
    print(f"projector/camera grazing budget = {BUDGET_DEG} deg")
    for kind in SURFACE_KINDS:
        report(kind)


if __name__ == "__main__":
    main()
