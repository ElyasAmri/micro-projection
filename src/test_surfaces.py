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
