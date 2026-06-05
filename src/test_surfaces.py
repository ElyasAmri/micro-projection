"""test_surfaces.py — Pure-NumPy heightmap generators for the simulator.

The Stage 4 GUI feeds these heightmaps into the math pipeline as ground-
truth surfaces. They are the "object" side of the simulation — what
`geometry.height_to_phase` consumes and what the recovered map is
compared against.

Units
-----
- Grid coordinates are mm. The (X, Y) mesh is centered on the grid
  origin: pixel `c` along axis 1 maps to `x = (c - (W-1)/2) * pixel_size_mm`,
  and pixel `r` along axis 0 maps to `y = (r - (H-1)/2) * pixel_size_mm`.
  For even H or W the origin lies between pixels; for odd H or W it
  lies on a pixel.
- All heights are mm.
- `pixel_size_mm` is isotropic (single scalar). The GUI's SURFACE_SHAPE
  = (550, 680) at SURFACE_PIXEL_SIZE_MM = 0.1 gives a rendered patch of
  68 x 55 mm — an exact match to the advertised camera FOV. Real
  hardware at 1280 x 1024 / 6.14 x 4.92 mm sensor / 0.09x M has
  slightly anisotropic pitches (~0.053 horizontal, ~0.054 vertical);
  the GUI's isotropic 0.1 mm/px is accepted for v1 and will be
  reconciled when real hardware values land in Stage 5/6.

Conventions
-----------
- Shape arg is `(H, W) = (rows, cols)` per NumPy convention. axis 0 = Y
  (vertical), axis 1 = X (horizontal).
- All surfaces are centered on the grid by construction.
- All outputs are `np.float64` and have shape `(H, W)`.

Module scope
------------
- No GUI imports. Pure NumPy.
- No surface registry / metadata dict here — that belongs to the GUI
  module that consumes these functions.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np


def _centered_grid_mm(
    shape: Tuple[int, int], pixel_size_mm: float
) -> Tuple[np.ndarray, np.ndarray]:
    """Build a centered (X, Y) mm-mesh of shape `(H, W)`.

    Returns
    -------
    (X, Y) : tuple of ndarray, both shape (H, W), dtype float64
        Coordinates in mm with origin at the grid center. X varies along
        axis 1 (cols), Y along axis 0 (rows). `meshgrid(..., indexing='xy')`
        is used so axes align with NumPy image conventions.
    """
    H, W = shape
    x_mm = (np.arange(W, dtype=np.float64) - (W - 1) / 2.0) * pixel_size_mm
    y_mm = (np.arange(H, dtype=np.float64) - (H - 1) / 2.0) * pixel_size_mm
    return np.meshgrid(x_mm, y_mm, indexing="xy")


def make_flat(
    shape: Tuple[int, int],
    pixel_size_mm: float,
) -> np.ndarray:
    """Flat surface at h = 0 everywhere.

    Parameters
    ----------
    shape : (H, W)
        Grid shape in (rows, cols).
    pixel_size_mm : float
        Isotropic pixel pitch in mm. Unused for the flat surface but
        accepted to keep the signature uniform across generators.

    Returns
    -------
    ndarray of shape (H, W), dtype float64, all zeros.
    """
    return np.zeros(shape, dtype=np.float64)


def make_gaussian(
    shape: Tuple[int, int],
    pixel_size_mm: float,
    amplitude_mm: float = 0.5,
    sigma_mm: float = 8.0,
) -> np.ndarray:
    """Centered 2D Gaussian.

    h(x, y) = amplitude_mm * exp(-(x**2 + y**2) / (2 * sigma_mm**2))

    Peak at the grid center equals `amplitude_mm` (exact when both H and
    W are odd; off-by-one-pixel discretization shifts it slightly for
    even-shape grids).

    Defaults match Fig. 3-6 of CHAPTER2 of the reference thesis (a 0.5 mm
    Gaussian bump). Default sigma 8 mm puts the bump comfortably inside
    the 55 mm vertical FOV.

    Parameters
    ----------
    shape : (H, W)
    pixel_size_mm : float
    amplitude_mm : float
        Peak height at the grid center.
    sigma_mm : float
        Gaussian standard deviation in mm.

    Returns
    -------
    ndarray of shape (H, W), dtype float64.
    """
    X, Y = _centered_grid_mm(shape, pixel_size_mm)
    return amplitude_mm * np.exp(-(X * X + Y * Y) / (2.0 * sigma_mm * sigma_mm))


def make_steep_dome(
    shape: Tuple[int, int],
    pixel_size_mm: float,
    amplitude_px: float = 6000.0,
    sigma_px: float = 60.0,
) -> np.ndarray:
    """Centered steep dome in the MATH-PIXEL convention (Stage 6 B.3a).

    h(i, j) = amplitude_px * exp(-((j-jc)**2 + (i-ic)**2) / (2 * sigma_px**2))

    UNIT CONVENTION — deliberately different from the other generators.
    `make_flat`/`make_gaussian` build in mm; this one builds on the PIXEL grid
    with amplitude and sigma in pixel / equivalent-wavelength units (the same
    convention `geometry.p` and `lambda_eq` use). That is the only convention in
    which a golden's flanks can push the camera-observed fringe frequency past
    the ~0.5 cyc/px Nyquist wall: the pipeline reads heightmap VALUES through
    `lambda_eq` (px) and the carrier on the pixel grid, while mm heights at
    0.1 mm/px scale per-pixel gradients down 10x — a steep dome in mm would
    need a multi-metre amplitude. The defaults (amp 6000, sigma 60 px) give a
    max per-pixel gradient ~60.6, i.e. a steep flank at f ~0.7-0.83 cyc/px
    (well past Nyquist) over ~11% of the frame, the B.3a beyond-Nyquist regime.

    `pixel_size_mm` is accepted for signature uniformity with the other
    generators but is NOT used (the dome lives on the pixel grid). The 3D view
    will render the values at face value (Z ~ amplitude_px); the showcase's
    headline is the error map + the convention-agnostic dynamic-range ratios,
    not the absolute Z scale.

    Parameters
    ----------
    shape : (H, W)
    pixel_size_mm : float
        Accepted for signature uniformity; unused (pixel-grid dome).
    amplitude_px : float
        Peak height in the math-pixel / lambda_eq convention.
    sigma_px : float
        Gaussian standard deviation in pixel indices.

    Returns
    -------
    ndarray of shape (H, W), dtype float64, in the math-pixel convention.
    """
    H, W = shape
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    yc, xc = (H - 1) / 2.0, (W - 1) / 2.0
    return amplitude_px * np.exp(
        -(((xx - xc) ** 2 + (yy - yc) ** 2) / (2.0 * sigma_px * sigma_px))
    )


def make_demo_defect(
    shape: tuple[int, int],
    amplitude: float = 3.0,
    sigma_px: float | None = None,
) -> np.ndarray:
    """A fixed, off-center Gaussian bump — the Stage 6 B.2/B.3a demo "defect".

    Added onto the golden to form the measured part so the deviation map shows a
    defect popping out (the inverse-FPP-with-golden payoff). ONE hardcoded
    feature, gated by a visible "Inject demo defect" checkbox; a defect editor /
    golden-part library is deferred (B.3+).

    Convention: `amplitude` is in the SAME convention as the golden it's added
    to — the mm default (3.0, sigma ~0.05*min(H,W) px) suits the mm `make_gaussian`
    golden; for the math-pixel `make_steep_dome` golden the caller passes the
    pixel-convention values (STEEP_DEFECT_AMP_PX / STEEP_DEFECT_SIGMA_PX), gentle
    enough that the defect's OWN gradient stays sub-Nyquist (so it survives the
    un-crushing — see the B.3a recon). Do not cross the two.
    """
    H, W = shape
    if sigma_px is None:
        sigma_px = 0.05 * float(min(H, W))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    yc, xc = 0.40 * H, 0.62 * W
    return amplitude * np.exp(
        -(((xx - xc) ** 2 + (yy - yc) ** 2) / (2.0 * sigma_px * sigma_px))
    )
