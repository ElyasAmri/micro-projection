"""Analytic test surfaces with known ground-truth height.

Reconstruction accuracy is only checkable against an *exact* answer, not a
guess -- these functions are that exact answer. Height convention: z
displacement in millimeters, added on top of the flat measurement plane
(z=0), as a function of (x_mm, y_mm) surface-plane coordinates.

Every surface here is kept to a max slope well under the rig's shadow-free
range (checked below, per surface) and a peak |h| well under lambda_eq/2 ~=
6.8mm (report/math.tex "Expected phase range"), so a single fringe
frequency resolves all of them unambiguously -- these test coverage of the
reconstruction math itself (different shapes, signs, symmetry, position),
not phase unwrapping, which this pipeline doesn't implement yet.

The footprint is ~87.5 x 54.7mm (report/math.tex "Matching distance"), so
every feature below is centered with at least ~2 sigma of margin from the
nearest edge (half-extents ~43.7 x 27.3mm).
"""
from __future__ import annotations

import numpy as np


def flat_height_mm(x_mm, y_mm):
    """Zero everywhere: the null case. Reconstruction should recover ~0
    height and its own noise floor, not the fringe pattern's own tilt --
    a bug in carrier-phase removal would show up here as a false slope."""
    return np.zeros_like(np.asarray(x_mm, dtype=float) + np.asarray(y_mm, dtype=float))


# A single smooth Gaussian bump. Max slope = A/sigma * exp(-1/2) (at r=sigma)
# ~= 0.607 * 3/15 ~= 0.121 rad ~= 6.9 degrees -- comfortably inside the rig's
# slope budget, so the bump doesn't self-shadow against either the projector
# or the camera. The original validation surface (report/math.tex sec.
# "Reconstruction validation").
BUMP_AMPLITUDE_MM = 3.0
BUMP_SIGMA_MM = 15.0
BUMP_CENTER_MM = (0.0, 0.0)


def bump_height_mm(x_mm, y_mm):
    """Known ground-truth deformity: a single Gaussian bump centered on the
    measurement plane. x_mm, y_mm may be scalars or numpy arrays."""
    cx, cy = BUMP_CENTER_MM
    r2 = (x_mm - cx) ** 2 + (y_mm - cy) ** 2
    return BUMP_AMPLITUDE_MM * np.exp(-r2 / (2.0 * BUMP_SIGMA_MM ** 2))


# Off-center and narrower than the main bump (max slope ~10.1 degrees) --
# tests that world-coordinate mapping is correct in both x and y, not just
# recovering a radially-symmetric shape that would look right even if a
# row/column axis were swapped.
OFFSET_BUMP_AMPLITUDE_MM = 3.5
OFFSET_BUMP_SIGMA_MM = 12.0
OFFSET_BUMP_CENTER_MM = (20.0, -10.0)


def offset_bump_height_mm(x_mm, y_mm):
    cx, cy = OFFSET_BUMP_CENTER_MM
    r2 = (x_mm - cx) ** 2 + (y_mm - cy) ** 2
    return OFFSET_BUMP_AMPLITUDE_MM * np.exp(-r2 / (2.0 * OFFSET_BUMP_SIGMA_MM ** 2))


# A dip (negative bump) -- tests the sign convention end to end.
CRATER_AMPLITUDE_MM = -2.5
CRATER_SIGMA_MM = 14.0
CRATER_CENTER_MM = (-15.0, 10.0)


def crater_height_mm(x_mm, y_mm):
    cx, cy = CRATER_CENTER_MM
    r2 = (x_mm - cx) ** 2 + (y_mm - cy) ** 2
    return CRATER_AMPLITUDE_MM * np.exp(-r2 / (2.0 * CRATER_SIGMA_MM ** 2))


# A ridge: Gaussian in x only, constant along y -- an anisotropic shape with
# no radial symmetry, running the full length of the footprint.
RIDGE_AMPLITUDE_MM = 2.5
RIDGE_SIGMA_X_MM = 10.0
RIDGE_CENTER_X_MM = 0.0


def ridge_height_mm(x_mm, y_mm):
    dx2 = (x_mm - RIDGE_CENTER_X_MM) ** 2
    return RIDGE_AMPLITUDE_MM * np.exp(-dx2 / (2.0 * RIDGE_SIGMA_X_MM ** 2)) * np.ones_like(np.asarray(y_mm, dtype=float))


# Two separated bumps -- tests a more complex field than a single lobe.
TWIN_BUMP_A_MM = (2.0, (-25.0, 12.0), 10.0)   # amplitude, center, sigma
TWIN_BUMP_B_MM = (2.5, (22.0, -12.0), 10.0)


def twin_bump_height_mm(x_mm, y_mm):
    total = np.zeros_like(np.asarray(x_mm, dtype=float) + np.asarray(y_mm, dtype=float))
    for amplitude, (cx, cy), sigma in (TWIN_BUMP_A_MM, TWIN_BUMP_B_MM):
        r2 = (x_mm - cx) ** 2 + (y_mm - cy) ** 2
        total = total + amplitude * np.exp(-r2 / (2.0 * sigma ** 2))
    return total


SURFACES = {
    "flat": flat_height_mm,
    "bump": bump_height_mm,
    "offset_bump": offset_bump_height_mm,
    "crater": crater_height_mm,
    "ridge": ridge_height_mm,
    "twin_bump": twin_bump_height_mm,
}
