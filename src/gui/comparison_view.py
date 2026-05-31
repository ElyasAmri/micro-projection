"""comparison_view.py — recovered vs. ground-truth 3D comparison view.

Stage 5 sub-task 4. A standalone GL view for the future "Recovered Surface"
4th tab: ONE GLViewWidget holding a labeled CoordinateGrid plus two surfaces
on the shared (550, 680) 0.1 mm/px grid:
  - the SOLID/OPAQUE recovered surface (steel-blue), and
  - the TRANSLUCENT ground-truth surface (amber, alpha 0.5) drawn over it,
each independently show/hide-able, both ON by default.

Solid-uniform colors (not viridis-on-height) are deliberate: they keep surface
IDENTITY (which surface is which) and DIVERGENCE (where they differ) in
separate visual channels. Blue/amber is also a colorblind-safe pairing.

No HardwareScene: this tab is just the two surfaces + grid. The render path
never touches the apparatus, so the view builds its own GLSurfacePlotItems
directly via the shared surface_render helper.

Honest scale: Z is rendered 1x (Z_EXAGGERATION doctrine) — the grid's Z axis
and the surfaces share real mm.
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pyqtgraph.opengl as gl
from PyQt6.QtWidgets import QWidget

from src.gui.coordinate_grid import CoordinateGrid
from src.gui.surface_render import apply_heightmap

# Default math grid (matches main_window.SURFACE_SHAPE / SURFACE_PIXEL_SIZE_MM;
# passed explicitly by the tab wiring in sub-task 5 to avoid importing
# main_window here, which would be a circular import).
DEFAULT_SHAPE: Tuple[int, int] = (550, 680)
DEFAULT_PIXEL_SIZE_MM: float = 0.1

# Solid-uniform surface colors (RGBA floats 0..1).
_RECOVERED_COLOR = (0.40, 0.55, 0.72, 1.0)        # opaque steel-blue
_GROUND_TRUTH_COLOR = (0.95, 0.65, 0.20, 0.5)     # translucent amber, alpha 0.5


class RecoveredComparisonView(gl.GLViewWidget):
    """Recovered (opaque) + ground-truth (translucent) over a labeled grid."""

    def __init__(
        self,
        shape: Tuple[int, int] = DEFAULT_SHAPE,
        pixel_size_mm: float = DEFAULT_PIXEL_SIZE_MM,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setBackgroundColor((30, 30, 30))
        self._shape = shape
        self._pixel_size_mm = pixel_size_mm

        # Labeled XYZ grid (4d.3). Z extent updated in set_data.
        self._grid = CoordinateGrid(shape, pixel_size_mm)
        self._grid.add_to(self)

        # Recovered: SOLID/OPAQUE, default glOptions, added FIRST.
        self._recovered_item = gl.GLSurfacePlotItem(
            shader="shaded", smooth=False, drawEdges=False
        )
        self.addItem(self._recovered_item)

        # Ground truth: TRANSLUCENT overlay. This is the exact construction
        # validated by the Stage 5 sub-task 1 (4d.1) translucent-primitive
        # probe (the probe script was deleted; the finding lived only in chat,
        # so it is recorded here):
        #   GLSurfacePlotItem + per-vertex colors with alpha < 1
        #   + setGLOptions("translucent") + setDepthValue(1).
        # setGLOptions("translucent") is LOAD-BEARING — without it pyqtgraph
        # 0.14.0 silently IGNORES the alpha and renders opaque (probe config
        # B0). With it, the blend is clean (no color inversion) on
        # pyqtgraph 0.14.0 / Qt 6.11.0, superseding the pre-4d.1 alpha-bug
        # note in PROJECT_CONTEXT §14 / stl_browser.py. depthValue(1) makes
        # the translucent surface draw AFTER the opaque recovered surface.
        self._ground_truth_item = gl.GLSurfacePlotItem(
            shader="shaded", smooth=False, drawEdges=False
        )
        self._ground_truth_item.setGLOptions("translucent")
        self._ground_truth_item.setDepthValue(1)
        self.addItem(self._ground_truth_item)

        # Both surfaces visible by default (GLGraphicsItem defaults to
        # visible; set explicitly for clarity).
        self._recovered_item.setVisible(True)
        self._ground_truth_item.setVisible(True)

        # Seed both items with flat zero data so the view paints cleanly if
        # it's shown before the first real set_data (an empty GLSurfacePlotItem
        # has no vertices and throws in faceNormals on paint).
        zeros = np.zeros(shape, dtype=np.float64)
        self.set_data(zeros, zeros)

        # Framed for the FOV-sized scene (~68 x 55 mm), no hardware bodies.
        self.setCameraPosition(distance=150, elevation=28, azimuth=45)

    # -- public API ----------------------------------------------------------
    def set_data(
        self,
        recovered_mm: np.ndarray,
        ground_truth_mm: np.ndarray,
    ) -> None:
        """Render both surfaces and fit the grid's Z axis to their combined
        height range. Both arrays are (H, W) float64 mm on the same grid."""
        recovered_mm = np.asarray(recovered_mm, dtype=np.float64)
        ground_truth_mm = np.asarray(ground_truth_mm, dtype=np.float64)

        apply_heightmap(
            self._recovered_item,
            recovered_mm,
            self._solid_colors(recovered_mm.shape, _RECOVERED_COLOR),
            self._pixel_size_mm,
        )
        apply_heightmap(
            self._ground_truth_item,
            ground_truth_mm,
            self._solid_colors(ground_truth_mm.shape, _GROUND_TRUTH_COLOR),
            self._pixel_size_mm,
        )

        # Z axis spans whatever either surface reaches.
        z_min = min(float(recovered_mm.min()), float(ground_truth_mm.min()))
        z_max = max(float(recovered_mm.max()), float(ground_truth_mm.max()))
        self._grid.set_z_extent(z_min, z_max)

    def set_recovered_visible(self, visible: bool) -> None:
        self._recovered_item.setVisible(bool(visible))

    def set_ground_truth_visible(self, visible: bool) -> None:
        self._ground_truth_item.setVisible(bool(visible))

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _solid_colors(
        shape: Tuple[int, int],
        rgba: Tuple[float, float, float, float],
    ) -> np.ndarray:
        """(H, W, 4) float32 field filled with a single RGBA color."""
        H, W = shape
        colors = np.empty((H, W, 4), dtype=np.float32)
        colors[..., 0] = rgba[0]
        colors[..., 1] = rgba[1]
        colors[..., 2] = rgba[2]
        colors[..., 3] = rgba[3]
        return colors
