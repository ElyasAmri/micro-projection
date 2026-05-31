"""surface_render.py — shared heightmap -> GLSurfacePlotItem render core.

Stage 5 sub-task 4. Single source of truth for the pyqtgraph 0.14.0
convention used to push an (H, W) mm heightmap into a `GLSurfacePlotItem`:
the centered coordinate grid and the two transposes/reshapes that the
library's quirky API requires. Extracted from `SurfacePreview` so both it and
the Stage 5 comparison view render identically (and so the quirk lives in one
place — it is also mirrored, for the grid extent only, in coordinate_grid.py).

Dependency-light on purpose: numpy + pyqtgraph only. No HardwareScene, no Qt
widgets, no other gui modules — importable by any view without drag-in.

Coordinate / axis convention (matches test_surfaces.py & coordinate_grid.py)
---------------------------------------------------------------------------
- X horizontal (mm), Y vertical (mm), Z height (mm).
- (H, W) heightmaps: axis 0 = Y (rows), axis 1 = X (cols).
- Centered grid: pixel (r, c) maps to
      x = (c - (W-1)/2) * pixel_size_mm
      y = (r - (H-1)/2) * pixel_size_mm

pyqtgraph quirks baked in here (do not re-derive elsewhere)
-----------------------------------------------------------
- `GLSurfacePlotItem.setData` wants `z` indexed `z[x_idx, y_idx]`, i.e. the
  transpose of our (H, W) -> (W, H). We pass `z=heightmap.T`.
- The `colors` argument's docstring claims `(width, height, 4)` but the value
  is passed straight to `MeshData.setVertexColors`, which needs the flat
  `(N_vertices, 4)` form, C-ordered over the (W, H) grid. We build colors in
  our (H, W, 4) layout, transpose to (W, H, 4), and reshape to (W*H, 4).
"""
from __future__ import annotations

from typing import Tuple

import numpy as np
import pyqtgraph as pg


def _build_diverging_colormap() -> pg.ColorMap:
    """Return a blue-white-red diverging colormap for signed errors.

    Primary: pyqtgraph's bundled CET-D1 (perceptually balanced).
    Fallback: hand-rolled blue->white->red ramp if CET-D1 fails to load
    (e.g., a pyqtgraph install missing its color-map data).
    """
    try:
        return pg.colormap.get("CET-D1")
    except Exception:
        return pg.ColorMap(
            pos=[0.0, 0.5, 1.0],
            color=[(20, 60, 200, 255), (255, 255, 255, 255), (200, 30, 30, 255)],
        )


# Module-level diverging colormap, the single source of truth shared by the
# error-coloring helper below, SurfacePreview's overlay, the comparison view,
# and the ErrorColorbar legend — so surface colors and the legend match.
ERROR_COLORMAP: pg.ColorMap = _build_diverging_colormap()


def error_colors(error: np.ndarray) -> np.ndarray:
    """Map a signed-error (H, W) array to (H, W, 4) float32 RGBA.

    Diverging colormap, symmetric about zero: error in [-|max|, +|max|] maps
    to colormap lookup [0, 1] (0.5 = zero error = the colormap center). An
    all-zero (or near-zero) field fills with the mid color. NaNs map to the
    center. Shared by SurfacePreview and the comparison view.
    """
    abs_max = float(np.nanmax(np.abs(error)))
    if abs_max < 1e-15:
        mid = ERROR_COLORMAP.map(
            np.array([0.5], dtype=np.float64), mode="float"
        )[0]
        colors = np.broadcast_to(mid, error.shape + (4,)).astype(np.float32)
        return np.ascontiguousarray(colors)
    normalized = np.where(
        np.isnan(error),
        0.5,
        (error / abs_max + 1.0) / 2.0,
    )
    return ERROR_COLORMAP.map(normalized, mode="float").astype(np.float32)


def centered_coords(
    shape: Tuple[int, int],
    pixel_size_mm: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Centered X (len W) and Y (len H) coordinate arrays in mm.

    Pure (no Qt/GL). `shape` is (H, W). The arrays place the grid center at
    the origin, matching the surface vertices and the CoordinateGrid extent.
    """
    H, W = shape
    x = (np.arange(W, dtype=np.float64) - (W - 1) / 2.0) * pixel_size_mm
    y = (np.arange(H, dtype=np.float64) - (H - 1) / 2.0) * pixel_size_mm
    return x, y


def apply_heightmap(
    item,
    heightmap_mm: np.ndarray,
    colors_hw4: np.ndarray,
    pixel_size_mm: float,
    z_exaggeration: float = 1.0,
) -> None:
    """Push an (H, W) heightmap + (H, W, 4) per-vertex RGBA into `item`.

    `item` is a `pyqtgraph.opengl.GLSurfacePlotItem`. Applies the centered
    grid and the (H, W) -> (W, H) z transpose and (H, W, 4) -> (W*H, 4) colors
    reshape (see module docstring). `z_exaggeration` is display-only; keep it
    at 1.0 for the honest-scale doctrine.
    """
    heightmap_mm = np.asarray(heightmap_mm, dtype=np.float64)
    H, W = heightmap_mm.shape
    x, y = centered_coords((H, W), pixel_size_mm)
    colors_flat = (
        np.asarray(colors_hw4, dtype=np.float32)
        .transpose(1, 0, 2)
        .reshape(-1, 4)
    )
    item.setData(
        x=x,
        y=y,
        z=(heightmap_mm * z_exaggeration).T,
        colors=colors_flat,
    )
