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
from src.gui.surface_render import apply_heightmap, error_colors

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

        # Display state. `_error_mm` None = solid-blue recovered + amber GT
        # (default); an array = recolor recovered by signed error AND
        # render-suppress the GT (sub-task 6). User visibility intent is
        # tracked separately so suppression never mutates the checkboxes.
        self._recovered_mm: Optional[np.ndarray] = None
        self._error_mm: Optional[np.ndarray] = None
        self._recovered_user_visible = True
        self._gt_user_visible = True

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
        z_max_percentile: Optional[float] = None,
    ) -> None:
        """Render both surfaces and fit the grid's Z axis to their combined
        height range. Both arrays are (H, W) float64 mm on the same grid.

        The recovered surface is colored per the current error-coloring mode
        (solid blue, or by signed error if `set_error_coloring` is active);
        the ground truth is amber, render-suppressed in error mode.

        `z_max_percentile` (Stage 6 B.3 polish) shapes ONLY the grid's view
        bounds, never the data. `None` (default) fits z_max to the raw combined
        max — the historical behavior, byte-identical for all existing callers.
        A float P fits z_max to the P-th percentile of the COMBINED displayed
        arrays instead, so a single extreme peak (the steep-dome center) sits
        outside the box rather than crushing all other detail flat. The arrays
        themselves are passed to the render untouched (honest scale, z=1.0); the
        peak simply exceeds the box. z_min is always the raw combined min.
        """
        recovered_mm = np.asarray(recovered_mm, dtype=np.float64)
        ground_truth_mm = np.asarray(ground_truth_mm, dtype=np.float64)
        self._recovered_mm = recovered_mm

        self._render_recovered()
        apply_heightmap(
            self._ground_truth_item,
            ground_truth_mm,
            self._solid_colors(ground_truth_mm.shape, _GROUND_TRUTH_COLOR),
            self._pixel_size_mm,
        )
        self._apply_gt_visibility()

        # Z axis spans whatever either surface reaches. z_min is always the raw
        # combined min; z_max is the raw combined max (default) or the requested
        # percentile of the combined displayed arrays (view-bounds only — the
        # data is unchanged).
        z_min = min(float(recovered_mm.min()), float(ground_truth_mm.min()))
        if z_max_percentile is None:
            z_max = max(float(recovered_mm.max()), float(ground_truth_mm.max()))
        else:
            combined = np.concatenate(
                (recovered_mm.ravel(), ground_truth_mm.ravel())
            )
            z_max = float(np.percentile(combined, z_max_percentile))
        self._grid.set_z_extent(z_min, z_max)

    def set_error_coloring(self, error_mm: Optional[np.ndarray]) -> None:
        """Switch the recovered surface between solid blue and error coloring.

        `None` -> solid steel-blue recovered + amber GT restored to the user's
        visibility choice. An (H, W) signed-error array -> recolor recovered by
        `error_colors(error)` AND render-suppress the GT (showing both the
        error map and the geometric overlay double-encodes divergence). The GT
        checkbox state is NOT mutated — suppression is purely render-time.
        """
        self._error_mm = (
            None if error_mm is None
            else np.asarray(error_mm, dtype=np.float64)
        )
        self._render_recovered()
        self._apply_gt_visibility()

    def set_recovered_visible(self, visible: bool) -> None:
        self._recovered_user_visible = bool(visible)
        self._recovered_item.setVisible(bool(visible))

    def set_ground_truth_visible(self, visible: bool) -> None:
        self._gt_user_visible = bool(visible)
        self._apply_gt_visibility()

    # -- internal render ------------------------------------------------------
    def _render_recovered(self) -> None:
        """(Re)color the recovered surface for the current mode."""
        if self._recovered_mm is None:
            return
        if self._error_mm is None:
            colors = self._solid_colors(self._recovered_mm.shape, _RECOVERED_COLOR)
        else:
            colors = error_colors(self._error_mm)
        apply_heightmap(
            self._recovered_item,
            self._recovered_mm,
            colors,
            self._pixel_size_mm,
        )

    def _apply_gt_visibility(self) -> None:
        """GT is visible iff the user wants it AND we're not in error mode."""
        self._ground_truth_item.setVisible(
            self._gt_user_visible and self._error_mm is None
        )

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
