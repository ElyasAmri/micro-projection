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


# A rough surface: a large smooth *form* (waviness) with a small, band-limited
# *roughness* texture on top -- the specimen the multi-frequency ladder exists
# to measure (report/math.tex "Roughness"; Chapter 3's form-vs-finish split).
# The two live in cleanly separated spatial bands so an ISO-25178 Gaussian
# high-pass (roughness.gaussian_highpass) recovers the texture without form
# bleed:
#   * form: a broad dome, sigma 25mm -> dominant wavelength ~100mm (>> cutoff),
#   * texture: a deterministic sum of sinusoids at 2.5-6mm wavelengths -- above
#     ~2x the finest rung's projected fringe period (1.09mm at n=80), so it's
#     actually resolvable, and below a ~10mm form/roughness cutoff.
# Deterministic (a fixed sinusoid sum, not a random draw) so it's an exact
# function of (x, y): the forward model and the ground-truth score evaluate the
# identical texture at identical world coords. Amplitudes are in micrometres.
ROUGH_FORM_AMPLITUDE_MM = 1.5
ROUGH_FORM_SIGMA_MM = 25.0
# (wavelength_mm, orientation_deg, amplitude_um, phase_rad)
_ROUGH_TEXTURE = (
    (6.0, 10.0, 20.0, 0.0),
    (4.0, 75.0, 15.0, 1.3),
    (3.0, 130.0, 12.0, 2.1),
    (2.5, 40.0, 10.0, 0.7),
)


def rough_height_mm(x_mm, y_mm):
    """Broad dome (form) + a band-limited sinusoidal texture (roughness). The
    texture's areal Sa/Sq (~tens of um) is what roughness.py recovers after the
    form is filtered out."""
    x = np.asarray(x_mm, dtype=float)
    y = np.asarray(y_mm, dtype=float)
    r2 = x ** 2 + y ** 2
    form = ROUGH_FORM_AMPLITUDE_MM * np.exp(-r2 / (2.0 * ROUGH_FORM_SIGMA_MM ** 2))
    texture = np.zeros_like(x + y)
    for wavelength_mm, angle_deg, amp_um, phase in _ROUGH_TEXTURE:
        angle = np.radians(angle_deg)
        proj = x * np.cos(angle) + y * np.sin(angle)  # distance along the wave's direction
        texture = texture + (amp_um / 1000.0) * np.cos(2.0 * np.pi * proj / wavelength_mm + phase)
    return form + texture


SURFACES = {
    "flat": flat_height_mm,
    "bump": bump_height_mm,
    "offset_bump": offset_bump_height_mm,
    "crater": crater_height_mm,
    "ridge": ridge_height_mm,
    "twin_bump": twin_bump_height_mm,
    "rough": rough_height_mm,
}
