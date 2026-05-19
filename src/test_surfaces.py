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
- `pixel_size_mm` is isotropic (single scalar). The real hardware FOV is
  68 mm x 55 mm at 1280 x 1024 native, which gives slightly anisotropic
  pixel pitches (~0.053 mm horizontal, ~0.054 mm vertical). The GUI
  downsamples to 480 x 640, where the anisotropy is still small
  (~0.106 vs ~0.115 mm/px). The isotropic approximation is accepted for
  v1; revisit if the lab calibration shows it matters.

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
