"""surface_preview.py — 3D heightmap renderer for the Stage 4a GUI.

Wraps a pyqtgraph OpenGL view with a reference grid (z=0 plane) and a
single `GLSurfacePlotItem` that the GUI updates on every slider change.

Coordinate convention
---------------------
Matches `src/test_surfaces.py`:
- X horizontal (mm), Y vertical (mm), Z height (mm)
- (H, W) heightmaps: axis 0 = Y (rows), axis 1 = X (cols)
- Centered grid: pixel (r, c) maps to
      x = (c - (W-1)/2) * pixel_size_mm
      y = (r - (H-1)/2) * pixel_size_mm
- Pixel pitch fixed at 0.1 mm for Stage 4a; tying it to a
  hardware-derived value comes later when the info panel goes live.

pyqtgraph axis + colors quirk
-----------------------------
`GLSurfacePlotItem.setData` requires `z.shape == (len(x), len(y))`,
i.e., z is indexed `z[x_idx, y_idx]` — the transpose of our (H, W)
heightmap, where axis 0 is rows = Y. `update_heightmap` passes
`z=heightmap.T` (a view, no copy).

The `colors` argument's docstring ("(width, height, 4) array of
vertex colors") in pyqtgraph 0.14.0 is wrong — the value is passed
straight to `MeshData.setVertexColors`, which requires the flat
(N_vertices, 4) shape. Vertex flat-order is C-order over the (W, H)
grid: vertex (i, j) sits at flat index `i*H + j`. We therefore
build colors in our (H, W, 4) layout, transpose to (W, H, 4), and
flatten C-order to (W*H, 4) before pushing to setData.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from PyQt6.QtWidgets import QWidget


# Locked at the launch-default Stage 4a grid. Revisit when the info
# panel exposes hardware-derived pitch.
DEFAULT_PIXEL_SIZE_MM = 0.1


class SurfacePreview(gl.GLViewWidget):
    """3D surface plot of a (H, W) heightmap with reference grid."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setBackgroundColor((30, 30, 30))

        self._pixel_size_mm = DEFAULT_PIXEL_SIZE_MM
        # Cached coordinate arrays; rebuilt on shape change.
        self._x: Optional[np.ndarray] = None
        self._y: Optional[np.ndarray] = None
        self._z_shape: Optional[tuple[int, int]] = None

        self._cmap = pg.colormap.get("viridis")

        self._add_reference_grid()
        self._surface_item = gl.GLSurfacePlotItem(
            shader="shaded", smooth=False, drawEdges=False
        )
        self.addItem(self._surface_item)

        # Camera tuned for the launch default — Gaussian (amp 0.5 mm,
        # sigma 8 mm) on a 480x640 grid (~64x48 mm footprint).
        self.setCameraPosition(distance=110, elevation=30, azimuth=45)

    def _add_reference_grid(self) -> None:
        """XY plane at z=0, 80x80 mm with 10 mm spacing."""
        grid = gl.GLGridItem()
        grid.setSize(x=80, y=80)
        grid.setSpacing(x=10, y=10)
        self.addItem(grid)

    def update_heightmap(self, heightmap_mm: np.ndarray) -> None:
        """Replace the rendered surface with the given (H, W) heightmap.

        Called by main_window on dropdown / slider changes. Recomputes
        per-vertex colors via the cached viridis colormap and pushes
        the new (x, y, z, colors) into the GLSurfacePlotItem.

        Performance note: at (480, 640) = 307,200 vertices, each call
        does one O(H*W) colormap lookup and one OpenGL buffer upload.
        If slider drag feels sluggish, downsample inside this method
        as a future optimization.
        """
        H, W = heightmap_mm.shape
        if self._z_shape != (H, W):
            self._rebuild_coordinate_arrays((H, W))

        colors = self._compute_colors(heightmap_mm)

        # pyqtgraph wants z[x_idx, y_idx] -> transpose our (H, W) to (W, H).
        # colors must be flat (W*H, 4) in C-order matching the vertex
        # enumeration; see module docstring "pyqtgraph axis + colors quirk".
        self._surface_item.setData(
            x=self._x,
            y=self._y,
            z=heightmap_mm.T,
            colors=colors.transpose(1, 0, 2).reshape(-1, 4),
        )

    def _rebuild_coordinate_arrays(self, shape: tuple[int, int]) -> None:
        H, W = shape
        ps = self._pixel_size_mm
        self._x = (np.arange(W, dtype=np.float64) - (W - 1) / 2.0) * ps
        self._y = (np.arange(H, dtype=np.float64) - (H - 1) / 2.0) * ps
        self._z_shape = shape

    def _compute_colors(self, z: np.ndarray) -> np.ndarray:
        """Map heightmap z values to per-vertex RGBA via viridis.

        Normalizes z to [0, 1] using its own min/max. Falls back to
        zeros when z is constant (e.g., make_flat or amplitude_mm=0)
        to avoid division-by-zero. Returns float32 (H, W, 4).
        """
        z_min = float(z.min())
        z_max = float(z.max())
        if z_max > z_min:
            z_norm = (z - z_min) / (z_max - z_min)
        else:
            z_norm = np.zeros_like(z)
        return self._cmap.map(z_norm, mode="float").astype(np.float32)
