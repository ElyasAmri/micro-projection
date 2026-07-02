"""Analytic test surfaces with known ground-truth height.

Reconstruction accuracy is only checkable against an *exact* answer, not a
guess -- these functions are that exact answer. Height convention: z
displacement in millimeters, added on top of the flat measurement plane
(z=0), as a function of (x_mm, y_mm) surface-plane coordinates.
"""
from __future__ import annotations

import math

# A single smooth Gaussian bump. Max slope = A/sigma * exp(-1/2) (at r=sigma)
# ~= 0.607 * 3/15 ~= 0.121 rad ~= 6.9 degrees -- comfortably inside the rig's
# slope budget, so the bump doesn't self-shadow against either the projector
# or the camera.
BUMP_AMPLITUDE_MM = 3.0
BUMP_SIGMA_MM = 15.0
BUMP_CENTER_MM = (0.0, 0.0)


def bump_height_mm(x_mm: float, y_mm: float) -> float:
    """Known ground-truth deformity: a single Gaussian bump centered on the
    measurement plane."""
    cx, cy = BUMP_CENTER_MM
    r2 = (x_mm - cx) ** 2 + (y_mm - cy) ** 2
    return BUMP_AMPLITUDE_MM * math.exp(-r2 / (2.0 * BUMP_SIGMA_MM ** 2))
