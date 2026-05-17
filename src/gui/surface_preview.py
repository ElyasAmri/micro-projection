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
- Z is scaled by `Z_EXAGGERATION` (display-only) before rendering.
  `self._last_heightmap` caches the unscaled array; error statistics
  in `main_window` operate on unscaled values.

Rendering modes
---------------
`update_heightmap(heightmap_mm)` (default): renders the surface
colored by height via the viridis colormap.

`update_heightmap(heightmap_mm, error_mm=err)`: renders the
**heightmap's shape** but colors the surface by the **signed error
array** via a diverging blue-white-red colormap, symmetric about zero.
Used for the error-overlay toggle in main_window.

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
from PyQt6.QtGui import QColor, QLinearGradient, QPainter
from PyQt6.QtWidgets import QWidget

from src.gui.hardware_scene import HardwareScene


# Locked at the launch-default Stage 4a grid. Revisit when the info
# panel exposes hardware-derived pitch.
DEFAULT_PIXEL_SIZE_MM = 0.1

# Display Z scale factor. Set to 1.0 (honest scale) at Stage 4b
# task 4 close: with the hardware bodies now in the scene at real
# scale, the surface render IS a geometric ruler — when the user
# sees the surface touch the (graying) lens, that must literally
# mean the surface height equals the clip-detection threshold. Any
# exaggeration would desync the visual from the clip math.
#
# Exaggeration (2.0) was useful in Stage 4a when the surface was
# alone in the scene with nothing to scale against. Now the
# hardware provides the scale reference, so exaggeration becomes
# distortion. Trade-off accepted: sub-mm specimens visually vanish
# in the 3D dome at 1×; the error overlay (diverging colormap) is
# the tool for seeing fine surface variation — the 3D dome only
# conveys macro shape.
Z_EXAGGERATION: float = 1.0


def _build_diverging_colormap() -> pg.ColorMap:
    """Return a blue-white-red diverging colormap for signed errors.

    Primary: pyqtgraph's bundled CET-D1 (perceptually balanced).
    Fallback: hand-rolled blue->white->red ramp if CET-D1 fails to
    load (e.g., a pyqtgraph install missing its color-map data).
    """
    try:
        return pg.colormap.get("CET-D1")
    except Exception:
        return pg.ColorMap(
            pos=[0.0, 0.5, 1.0],
            color=[(20, 60, 200, 255), (255, 255, 255, 255), (200, 30, 30, 255)],
        )


# Module-level diverging colormap shared between SurfacePreview's error
# overlay and main_window's colorbar widget. Single source of truth so
# the legend matches the surface colors exactly.
ERROR_COLORMAP: pg.ColorMap = _build_diverging_colormap()


class ErrorColorbar(QWidget):
    """Horizontal colorbar showing the diverging colormap with labels.

    Rendered as a 16-px-tall color gradient strip with three numeric
    labels (left = -abs_max, center = 0, right = +abs_max) beneath it.
    Hidden by default; visibility and range are driven by
    `MainWindow._refresh_surface_preview`.
    """

    BAR_HEIGHT_PX: int = 16
    LABEL_AREA_PX: int = 18

    def __init__(
        self,
        cmap: pg.ColorMap = ERROR_COLORMAP,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._cmap = cmap
        self._abs_max: float = 0.0
        self.setFixedHeight(self.BAR_HEIGHT_PX + self.LABEL_AREA_PX)

    def set_range(self, abs_max: float) -> None:
        """Set the displayed range. Triggers a repaint."""
        self._abs_max = float(abs_max)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: D401, ARG002
        painter = QPainter(self)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def _paint(self, painter: QPainter) -> None:
        w = self.width()

        # Build a QLinearGradient by sampling the colormap.
        gradient = QLinearGradient(0, 0, w, 0)
        N = 32
        for k in range(N + 1):
            t = k / N
            rgba = self._cmap.map(
                np.array([t], dtype=np.float64), mode="float"
            )[0]
            gradient.setColorAt(t, QColor.fromRgbF(
                float(rgba[0]), float(rgba[1]), float(rgba[2]),
                float(rgba[3]),
            ))
        painter.fillRect(0, 0, w, self.BAR_HEIGHT_PX, gradient)

        # Labels — left aligned, center, right aligned.
        painter.setPen(QColor("white"))
        font = painter.font()
        font.setFamily("monospace")
        font.setPointSize(8)
        painter.setFont(font)

        label_y = self.BAR_HEIGHT_PX + 14
        am = self._abs_max
        if not np.isfinite(am):
            am = 0.0
        left_text = self._format_label(-am)
        right_text = self._format_label(+am)
        if am > 0:
            right_text = "+" + right_text.lstrip()
        center_text = "0"

        metrics = painter.fontMetrics()
        painter.drawText(2, label_y, left_text)
        cw = metrics.horizontalAdvance(center_text)
        painter.drawText((w - cw) // 2, label_y, center_text)
        rw = metrics.horizontalAdvance(right_text)
        painter.drawText(w - rw - 2, label_y, right_text)

    @staticmethod
    def _format_label(value: float) -> str:
        """Match main_window's error-stat auto-format style."""
        if abs(value) < 1e-4 and value != 0.0:
            return f"{value:.2e}"
        return f"{value:.4f}"


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
        # Cached unscaled heightmap from the last update_heightmap call.
        # Task 4c may use this for the degenerate-warning logic.
        self._last_heightmap: Optional[np.ndarray] = None

        self._cmap_height = pg.colormap.get("viridis")
        # Use the module-level diverging cmap so the colorbar legend
        # in main_window draws from the same source.
        self._cmap_error = ERROR_COLORMAP

        self._add_reference_grid()
        self._surface_item = gl.GLSurfacePlotItem(
            shader="shaded", smooth=False, drawEdges=False
        )
        self.addItem(self._surface_item)

        # Stage 4b task 3: hardware bodies live in the same scene as
        # the recovered surface. `HardwareScene` adds 4 GLMeshItems
        # (camera body + lens, projector body + lens) at identity
        # transforms; main_window calls `update_hardware_pose` once
        # after construction to position them at slider defaults.
        self._hardware_scene = HardwareScene(self)

        # Camera tuned for the launch default — Gaussian (amp 0.5 mm,
        # sigma 8 mm) on a 480x640 grid (~64x48 mm footprint), with
        # Z_EXAGGERATION = 2 making a ~1-display-mm peak. Stage 4b
        # task 3: distance pulled back from 80 to 600 so the camera
        # assembly fits in frame. With WD=157 mm and a 200 mm lens,
        # the camera body sits 157 + 215 = 372 mm from the surface
        # along its arm — the scene now spans ~400 mm in z.
        self.setCameraPosition(distance=600, elevation=20, azimuth=45)

    def _add_reference_grid(self) -> None:
        """XY plane at z=0, sized large enough to read the lab apparatus.

        Stage 4b task 3: grid bumped from 80x80 mm (Stage 4a default,
        sized just for the surface footprint) to 300x300 mm so the
        camera/projector bodies at ~150 mm distance have a visible
        floor beneath them in the same scene.
        """
        grid = gl.GLGridItem()
        grid.setSize(x=300, y=300)
        grid.setSpacing(x=25, y=25)
        self.addItem(grid)

    def update_hardware_pose(
        self,
        theta_camera_deg: float,
        theta_projector_deg: float,
        projector_distance_mm: float,
        camera_distance_mm: float,
    ):
        """Push fresh poses into the hardware bodies + cones.

        Thin pass-through to `HardwareScene.update_pose`. Kept on the
        SurfacePreview class so main_window doesn't reach across into
        the HardwareScene directly. Returns the `ClipState` from the
        pose update so main_window can drive the clip-warning banner.
        """
        return self._hardware_scene.update_pose(
            theta_camera_deg=theta_camera_deg,
            theta_projector_deg=theta_projector_deg,
            projector_distance_mm=projector_distance_mm,
            camera_distance_mm=camera_distance_mm,
        )

    def update_heightmap(
        self,
        heightmap_mm: np.ndarray,
        error_mm: Optional[np.ndarray] = None,
    ) -> None:
        """Replace the rendered surface with the given (H, W) heightmap.

        Parameters
        ----------
        heightmap_mm : (H, W) ndarray
            Height in mm. Used for surface geometry; Z is scaled by
            `Z_EXAGGERATION` before rendering.
        error_mm : (H, W) ndarray, optional
            Signed error in mm. When provided, surface is colored by
            the error via a diverging colormap symmetric about zero;
            otherwise colored by height via viridis.

            All-NaN: falls back to height-viridis (no exception). The
            user sees a normal-looking surface; task 4c handles
            warning the user that the recovery is invalid.

            All-zero (or |max| < 1e-15): fills with the mid-colormap
            color (white for CET-D1) to avoid division-by-zero.

        Side effects
        ------------
        Caches the unscaled `heightmap_mm` as `self._last_heightmap`
        for task 4c hooks.
        """
        heightmap_mm = np.asarray(heightmap_mm, dtype=np.float64)
        self._last_heightmap = heightmap_mm

        H, W = heightmap_mm.shape
        if self._z_shape != (H, W):
            self._rebuild_coordinate_arrays((H, W))

        colors = self._compute_colors(heightmap_mm, error_mm)
        z_scaled = heightmap_mm * Z_EXAGGERATION

        # pyqtgraph wants z[x_idx, y_idx] -> transpose our (H, W) to (W, H).
        # colors must be flat (W*H, 4) in C-order matching the vertex
        # enumeration; see module docstring "pyqtgraph axis + colors quirk".
        self._surface_item.setData(
            x=self._x,
            y=self._y,
            z=z_scaled.T,
            colors=colors.transpose(1, 0, 2).reshape(-1, 4),
        )

    def _rebuild_coordinate_arrays(self, shape: tuple[int, int]) -> None:
        H, W = shape
        ps = self._pixel_size_mm
        self._x = (np.arange(W, dtype=np.float64) - (W - 1) / 2.0) * ps
        self._y = (np.arange(H, dtype=np.float64) - (H - 1) / 2.0) * ps
        self._z_shape = shape

    def _compute_colors(
        self,
        z: np.ndarray,
        error: Optional[np.ndarray],
    ) -> np.ndarray:
        """Map values to per-vertex RGBA, viridis-on-z or diverging-on-error.

        Returns float32 (H, W, 4).
        """
        if error is not None and not np.all(np.isnan(error)):
            return self._compute_error_colors(error)
        return self._compute_height_colors(z)

    def _compute_height_colors(self, z: np.ndarray) -> np.ndarray:
        """Viridis colormap on height range (task 3 default)."""
        z_min = float(z.min())
        z_max = float(z.max())
        if z_max > z_min:
            z_norm = (z - z_min) / (z_max - z_min)
        else:
            z_norm = np.zeros_like(z)
        return self._cmap_height.map(z_norm, mode="float").astype(np.float32)

    def _compute_error_colors(self, error: np.ndarray) -> np.ndarray:
        """Diverging colormap on signed error, symmetric about zero."""
        abs_max = float(np.nanmax(np.abs(error)))
        if abs_max < 1e-15:
            # All-zero (or near-zero) error: fill with the mid-colormap
            # color (0.5 lookup, the diverging center).
            mid = self._cmap_error.map(
                np.array([0.5], dtype=np.float64), mode="float"
            )[0]
            colors = np.broadcast_to(mid, error.shape + (4,)).astype(np.float32)
            return np.ascontiguousarray(colors)
        # Map error in [-abs_max, +abs_max] to lookup in [0, 1].
        # Replace NaN (mixed NaN within otherwise-finite array — shouldn't
        # happen under the all-NaN fall-through guard in _compute_colors,
        # but defensive) with 0.5 so it lands on the colormap center.
        normalized = np.where(
            np.isnan(error),
            0.5,
            (error / abs_max + 1.0) / 2.0,
        )
        return self._cmap_error.map(normalized, mode="float").astype(np.float32)
