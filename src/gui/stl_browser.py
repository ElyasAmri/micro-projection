"""stl_browser.py — Stage 4d Browser tab widget.

Third tab on the right-pane QTabWidget. Provides FOV-by-FOV
navigation of oversized STL specimens via a minimap + windowed
preview triad. Panels 1 (whole-STL) and 3 (windowed slice) ship
with real 3D rendering in sub-task 4; Panel 2 (minimap) stays
a placeholder until sub-task 5 adds the FOV-rectangle drag.

State dispatch
--------------
The widget exposes two views via an internal QStackedWidget:
  - placeholder: shown when no Browser-mode STL is active
    (no STL loaded, Flat / Gaussian selected, or a small STL
    on the direct path).
  - panels: shown when MainWindow's _stl_is_browser_mode is True.
MainWindow drives the switch via show_placeholder() /
show_panels(); the widget itself reads no cache state.

Rendering
---------
Panels 1 and 3 are pyqtgraph GLViewWidgets containing one lazily-
constructed GLSurfacePlotItem each. Coordinate convention and the
`z=heightmap.T` transpose match `surface_preview.py` so the
orientation is consistent across all 3D views in the GUI. No
colormap, no error overlay — the `shaded` shader's flat coloring
is sufficient for "show the shape."
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


_PLACEHOLDER_TEXT = (
    "Load an oversized STL (XY larger than 68 × 55 mm but within "
    "272 × 220 mm) to browse it FOV by FOV.\n\n"
    "Currently no Browser-mode STL is active. Small STLs use the "
    "3D Scene tab directly."
)


# Camera defaults. Panel 3 distance is intentionally smaller than
# SurfacePreview's 600 — Browser Panel 3 shows surface-only (no
# hardware bodies in the scene), so the closer pose keeps the
# 68 x 55 mm windowed surface readable. 30% frame fill at the
# default 60-deg GLViewWidget FOV. Elevation/azimuth still match
# SurfacePreview for orientational continuity.
_WINDOWED_CAMERA = dict(distance=200, elevation=20, azimuth=45)
# Panel 1 uses a 3/4-isometric pose at engineering-CAD conventional
# angles; distance scales to the part bbox (set inside update_whole_stl).
_WHOLE_STL_ELEVATION = 30
_WHOLE_STL_AZIMUTH = 45
_WHOLE_STL_DISTANCE_FACTOR = 1.5  # distance = 1.5 * max(bbox XY)

# FOV rectangle visual style. Bright cyan against the grayscale
# minimap stands out without conflicting with the lab view's
# blue/red diverging colormap or the gray hardware bodies.
_FOV_RECT_PEN = (0, 220, 255)
_FOV_RECT_WIDTH_PX = 2

# Panel 1 highlight visual style. RGBA normalized to [0, 1] for
# GLSurfacePlotItem. RGB matches _FOV_RECT_PEN / 255 for visual
# continuity — "the same region" across the minimap rectangle and
# Panel 1's surface-following overlay.
#
# pyqtgraph 0.14.0 (in this Qt OpenGL environment) has a
# rendering bug where alpha < 1.0 on GLSurfacePlotItem
# produces inverted-complement colors regardless of shader.
# Empirical: output_X ≈ 127 - 44 × input_X for alpha=0.5.
# Bug ruled out at the shader, the per-vertex-vs-constant
# color path, sibling-item state, glOptions/blending, and
# the color-input layer (full diagnostic chain in Stage 4d
# sub-task 5.5 captures, ~/AppData/Local/Temp/stage4d_st55_*).
# Workaround: use opaque cyan (alpha=1.0). Translucency was
# a nice-to-have, not load-bearing — Panel 3 shows the
# FOV contents directly, and the highlight's job is "show
# WHICH region" not "show through to underlying contour."
_FOV_HIGHLIGHT_COLOR_RGBA = (0.0, 220.0 / 255.0, 1.0, 1.0)
# Z-offset to lift the highlight above the part surface and avoid
# z-fighting. 0.05 mm is ~28000x the depth-buffer precision floor
# and sub-pixel at the 0.1 mm/px grid — sits "on" the surface
# visually without floating.
_FOV_HIGHLIGHT_Z_EPSILON_MM = 0.05


def _panel(label_text: str) -> QFrame:
    """Build a sunken QFrame containing a centered descriptive label.

    Sub-task 4 keeps this only for Panel 2 (minimap, sub-task 5 work).
    """
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    frame.setFrameShadow(QFrame.Shadow.Sunken)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(8, 8, 8, 8)
    label = QLabel(label_text)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    label.setStyleSheet("color: #888; font-size: 12px;")
    layout.addWidget(label)
    return frame


def _new_3d_view(distance: float, elevation: float, azimuth: float) -> gl.GLViewWidget:
    """Build a GLViewWidget with the shared Browser-panel camera."""
    view = gl.GLViewWidget()
    view.setBackgroundColor((30, 30, 30))
    view.setCameraPosition(
        distance=distance, elevation=elevation, azimuth=azimuth,
    )
    return view


class STLBrowser(QWidget):
    """Stage 4d Browser tab: FOV-by-FOV navigation of full-scale STLs.

    Three-panel layout when Browser-mode is active:
      - Top-left:    minimap (2D top-down with draggable FOV rectangle)
      - Bottom-left: whole-STL 3D preview (orientation only)
      - Right:       windowed 3D preview (what the math measures)
    Placeholder shown otherwise.

    Whole-STL and windowed views are driven by `update_whole_stl` and
    `update_windowed_slice` respectively. The two methods stay separate
    so the drag handler can refresh Panel 3 on every mouse move without
    redoing Panel 1's larger mesh.

    Drag signal
    -----------
    `fov_dragged((x_origin_mm, y_origin_mm))` fires on every RectROI
    move. MainWindow connects this to a slot that updates
    `_stl_fov_origin_mm`, calls `_extract_fov_slice`, and pushes the
    new slice via `update_windowed_slice`. The lab view and Pipeline
    Stages stay pinned to the most-recently-COMMITTED FOV — drag is
    Panel 3 only.

    Commit signal
    -------------
    `commit_fov_requested()` fires when the user clicks the "Commit
    FOV" button below the minimap (sub-task 6). No payload — the
    cached `_stl_heightmap` on MainWindow is already current from
    the drag handler. MainWindow's slot calls
    `_refresh_surface_preview` to propagate the cached slice to the
    lab view + Pipeline Stages + math pipeline.
    """

    fov_dragged = pyqtSignal(tuple)
    commit_fov_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._stack = QStackedWidget()

        # Page 0: placeholder.
        placeholder = QWidget()
        ph_layout = QVBoxLayout(placeholder)
        ph_layout.setContentsMargins(40, 40, 40, 40)
        ph_label = QLabel(_PLACEHOLDER_TEXT)
        ph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_label.setWordWrap(True)
        ph_label.setStyleSheet("color: #888; font-size: 13px;")
        ph_layout.addStretch(1)
        ph_layout.addWidget(ph_label)
        ph_layout.addStretch(1)
        self._stack.addWidget(placeholder)

        # Page 1: three-panel splitter layout.
        outer = QSplitter(Qt.Orientation.Horizontal)
        inner = QSplitter(Qt.Orientation.Vertical)

        # Panel 2 (top-left): minimap with draggable FOV rectangle.
        self._minimap = self._build_minimap()
        self._minimap_image_item: Optional[pg.ImageItem] = None
        self._minimap_roi: Optional[pg.RectROI] = None

        # Panel 1 (bottom-left): whole-STL 3D preview.
        self._whole_stl_view = _new_3d_view(
            distance=300,  # placeholder; updated per part in update_whole_stl
            elevation=_WHOLE_STL_ELEVATION,
            azimuth=_WHOLE_STL_AZIMUTH,
        )
        self._whole_stl_item: Optional[gl.GLSurfacePlotItem] = None
        # Sub-task 5.5: Panel 1 FOV highlight overlay. Second
        # GLSurfacePlotItem at the FOV-windowed region, lifted by
        # epsilon and rendered in translucent cyan. Added AFTER the
        # whole-STL item so it sits on top in the GLViewWidget's
        # scene-insertion order.
        self._whole_stl_highlight_item: Optional[gl.GLSurfacePlotItem] = None

        # Panel 3 (right): windowed 3D preview.
        self._windowed_view = _new_3d_view(**_WINDOWED_CAMERA)
        self._windowed_item: Optional[gl.GLSurfacePlotItem] = None

        # Sub-task 6: Commit FOV button. Lives in Panel 2's interaction
        # region (below the minimap). Wrapping the minimap + button in
        # a QVBoxLayout keeps the inner splitter two-region (minimap-
        # wrapper / whole-STL). Button initial state is disabled —
        # belt-and-suspenders against the show_panels/show_placeholder
        # dispatch path: __init__ uses setCurrentIndex(0) directly,
        # bypassing show_placeholder, so we lock the disabled state
        # here too.
        self.commit_fov_button = QPushButton("Commit FOV")
        self.commit_fov_button.setEnabled(False)
        self.commit_fov_button.clicked.connect(
            self.commit_fov_requested.emit
        )

        panel2_wrapper = QWidget()
        panel2_layout = QVBoxLayout(panel2_wrapper)
        panel2_layout.setContentsMargins(0, 0, 0, 0)
        panel2_layout.addWidget(self._minimap, 1)
        panel2_layout.addWidget(self.commit_fov_button, 0)

        inner.addWidget(panel2_wrapper)
        inner.addWidget(self._whole_stl_view)
        inner.setSizes([440, 360])  # ~55/45 within the left half

        outer.addWidget(inner)
        outer.addWidget(self._windowed_view)
        outer.setSizes([400, 600])  # ~40/60 of available width

        self._stack.addWidget(outer)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self._stack.setCurrentIndex(0)

    def _build_minimap(self) -> pg.GraphicsLayoutWidget:
        """Build the minimap container (no data yet)."""
        gw = pg.GraphicsLayoutWidget()
        gw.setBackground((30, 30, 30))
        self._minimap_plot = gw.addPlot()
        self._minimap_plot.setAspectLocked(True)
        self._minimap_plot.setMenuEnabled(False)
        self._minimap_plot.hideButtons()
        self._minimap_plot.setLabel("bottom", "X (mm)")
        self._minimap_plot.setLabel("left", "Y (mm)")
        return gw

    # ------------------------------------------------------------------
    # State-dispatch (sub-task 3)
    # ------------------------------------------------------------------
    @property
    def is_showing_panels(self) -> bool:
        """True when the three-panel layout is active; False for placeholder."""
        return self._stack.currentIndex() == 1

    def show_placeholder(self) -> None:
        """Switch to the placeholder view (no Browser-mode STL active)."""
        self._stack.setCurrentIndex(0)
        # Sub-task 6: commit only makes sense in Browser mode.
        self.commit_fov_button.setEnabled(False)

    def show_panels(self) -> None:
        """Switch to the three-panel layout (Browser-mode STL active)."""
        self._stack.setCurrentIndex(1)
        # Sub-task 6: enable the commit button once Browser mode is live.
        self.commit_fov_button.setEnabled(True)

    # ------------------------------------------------------------------
    # Content updates (sub-task 4)
    # ------------------------------------------------------------------
    @property
    def has_whole_stl_content(self) -> bool:
        """True when Panel 1's GLSurfacePlotItem has been constructed."""
        return self._whole_stl_item is not None

    @property
    def has_windowed_slice(self) -> bool:
        """True when Panel 3's GLSurfacePlotItem has been constructed."""
        return self._windowed_item is not None

    def update_whole_stl(
        self,
        heightmap: np.ndarray,
        pixel_size_mm: float,
    ) -> None:
        """Push the full-scale STL heightmap into Panel 1.

        Reconstructs (or reuses) a single GLSurfacePlotItem with the
        new data and repositions the camera so the part fits in view.
        Called by MainWindow at the end of `_load_stl_browser`. Each
        call replaces the prior content — items don't accumulate.
        """
        heightmap = np.asarray(heightmap, dtype=np.float64)
        H, W = heightmap.shape
        x = (np.arange(W, dtype=np.float64) - (W - 1) / 2.0) * pixel_size_mm
        y = (np.arange(H, dtype=np.float64) - (H - 1) / 2.0) * pixel_size_mm

        if self._whole_stl_item is None:
            self._whole_stl_item = gl.GLSurfacePlotItem(
                shader="shaded", smooth=False, drawEdges=False,
            )
            self._whole_stl_view.addItem(self._whole_stl_item)
        # pyqtgraph wants z[x_idx, y_idx] -> transpose our (H, W) to (W, H).
        self._whole_stl_item.setData(x=x, y=y, z=heightmap.T)

        # Scale camera distance to the part bbox so the part fills the
        # frame. Camera angles are reset to the isometric default so
        # repeated loads start from a known pose.
        part_w_mm = W * pixel_size_mm
        part_h_mm = H * pixel_size_mm
        distance = max(part_w_mm, part_h_mm) * _WHOLE_STL_DISTANCE_FACTOR
        self._whole_stl_view.setCameraPosition(
            distance=distance,
            elevation=_WHOLE_STL_ELEVATION,
            azimuth=_WHOLE_STL_AZIMUTH,
        )

    def update_windowed_slice(
        self,
        heightmap: np.ndarray,
        pixel_size_mm: float,
    ) -> None:
        """Push the current FOV slice into Panel 3.

        Reconstructs (or reuses) a single GLSurfacePlotItem. Camera
        pose is NOT reset between calls — the drag handler calls this
        on every mouse move and a jolting camera would be unusable.
        Initial pose comes from `__init__`.
        """
        heightmap = np.asarray(heightmap, dtype=np.float64)
        H, W = heightmap.shape
        x = (np.arange(W, dtype=np.float64) - (W - 1) / 2.0) * pixel_size_mm
        y = (np.arange(H, dtype=np.float64) - (H - 1) / 2.0) * pixel_size_mm

        if self._windowed_item is None:
            self._windowed_item = gl.GLSurfacePlotItem(
                shader="shaded", smooth=False, drawEdges=False,
            )
            self._windowed_view.addItem(self._windowed_item)
        self._windowed_item.setData(x=x, y=y, z=heightmap.T)

    @property
    def has_minimap_content(self) -> bool:
        """True when the minimap image+ROI have been constructed."""
        return self._minimap_image_item is not None

    def update_minimap(
        self,
        full_heightmap: np.ndarray,
        full_origin_mm: tuple[float, float],
        pixel_size_mm: float,
        fov_origin_mm: tuple[float, float],
        fov_shape_pixels: tuple[int, int],
    ) -> None:
        """Render the full-scale STL as a 2D top-down image with the
        draggable FOV rectangle overlaid.

        `full_origin_mm` = part-local (x_min, y_min) of the (0, 0)
        pixel of `full_heightmap`. Used to position the ImageItem in
        part-local plot coordinates so the user reads real mm on the
        axes.

        `fov_origin_mm` = part-local (x_origin, y_origin) of the FOV
        slice's bottom-left corner (matches `_stl_fov_origin_mm`
        convention; row 0 of the heightmap array = Y_min in plot
        coords, Y growing up).

        `fov_shape_pixels` = (H_fov, W_fov) for the FOV slice; the
        rectangle's physical size is `fov_shape_pixels * pixel_size_mm`.
        Passed in rather than imported from main_window to keep this
        widget decoupled from the constants module.

        Lazy-constructs the ImageItem and RectROI on first call;
        subsequent calls reuse the same items (no accumulation in the
        plot scene). The ROI's `setPos` happens under `blockSignals`
        so a programmatic reposition doesn't fire a spurious
        `fov_dragged` emit.
        """
        full_heightmap = np.asarray(full_heightmap, dtype=np.float64)
        H_full, W_full = full_heightmap.shape
        H_fov, W_fov = fov_shape_pixels
        x_min, y_min = full_origin_mm

        if self._minimap_image_item is None:
            # First call: create image item.
            self._minimap_image_item = pg.ImageItem(axisOrder="row-major")
            self._minimap_plot.addItem(self._minimap_image_item)

        self._minimap_image_item.setImage(full_heightmap)
        self._minimap_image_item.setRect(
            QRectF(
                x_min, y_min,
                W_full * pixel_size_mm, H_full * pixel_size_mm,
            )
        )

        if self._minimap_roi is None:
            # First call: create FOV rectangle.
            self._minimap_roi = pg.RectROI(
                pos=fov_origin_mm,
                size=(W_fov * pixel_size_mm, H_fov * pixel_size_mm),
                pen=pg.mkPen(_FOV_RECT_PEN, width=_FOV_RECT_WIDTH_PX),
                movable=True,
                resizable=False,
                rotatable=False,
            )
            # Belt-and-suspenders against pg-version drift: scrub any
            # default handles (RectROI adds a scale handle in __init__
            # regardless of `resizable=False` on some versions).
            while self._minimap_roi.handles:
                self._minimap_roi.removeHandle(
                    self._minimap_roi.handles[0]["item"]
                )
            self._minimap_plot.addItem(self._minimap_roi)
            self._minimap_roi.sigRegionChanged.connect(self._on_roi_changed)
        else:
            # Subsequent call: reposition under blockSignals to avoid
            # spurious emit during programmatic reposition.
            self._minimap_roi.blockSignals(True)
            self._minimap_roi.setPos(fov_origin_mm)
            self._minimap_roi.blockSignals(False)

        # Expand the initial view range by FULL-FOV padding on each
        # side so the FOV rectangle stays fully visible across the
        # full range of drag positions, including the worst case
        # where the rectangle is dragged its full extent off the
        # part. Rectangle bottom-left at part bbox edge => rectangle
        # outermost edge at bbox edge + FOV, fully covered by this
        # range. Trades initial-view tightness for guaranteed
        # visibility of the interaction target — silent "rectangle
        # dragged off-screen" failure is worse than cosmetic "part
        # looks slightly smaller in the minimap."
        full_fov_w = W_fov * pixel_size_mm
        full_fov_h = H_fov * pixel_size_mm
        self._minimap_plot.setXRange(
            x_min - full_fov_w,
            x_min + W_full * pixel_size_mm + full_fov_w,
            padding=0,
        )
        self._minimap_plot.setYRange(
            y_min - full_fov_h,
            y_min + H_full * pixel_size_mm + full_fov_h,
            padding=0,
        )

    def _on_roi_changed(self) -> None:
        """Emit fov_dragged with the ROI's current (x, y) in mm."""
        pos = self._minimap_roi.pos()
        self.fov_dragged.emit((float(pos[0]), float(pos[1])))

    # ------------------------------------------------------------------
    # Panel 1 FOV highlight overlay (sub-task 5.5)
    # ------------------------------------------------------------------
    @property
    def has_panel1_highlight(self) -> bool:
        """True when Panel 1's FOV highlight overlay is present."""
        return self._whole_stl_highlight_item is not None

    def update_panel1_highlight(
        self,
        full_heightmap: np.ndarray,
        full_origin_mm: tuple[float, float],
        pixel_size_mm: float,
        fov_origin_mm: tuple[float, float],
        fov_shape_pixels: tuple[int, int],
    ) -> None:
        """Update Panel 1's translucent cyan highlight to follow the
        part surface at the current FOV region.

        Slices the FOV-sized window from `full_heightmap` at the given
        origin (same arithmetic as MainWindow._extract_fov_slice but
        reads from the input array, not MainWindow state), positions
        a second GLSurfacePlotItem at the corresponding XY in the
        part-bbox-centered frame so it aligns with the existing
        whole-STL surface (which `update_whole_stl` centers at the
        origin). Z is lifted by `_FOV_HIGHLIGHT_Z_EPSILON_MM` to avoid
        z-fighting.

        Off-part regions (FOV extends past the full heightmap edges)
        get 0.0 fill — same convention as MainWindow._extract_fov_slice.
        The highlight visibly extends into bare stage at the edges so
        the user can see when their selection runs off the part.

        Color uses the GL constant-attribute path (`setColor` at
        lazy-construction). CRITICAL: do NOT pass colors= to setData.
        The sub-task 5.5 diagnostic showed per-vertex colors caused
        rendering corruption (maroon instead of cyan) due to GL state
        leakage between sibling GLSurfacePlotItems in the same view
        — the whole-STL item uses constant-attribute and the highlight
        item using buffer-backed-array introduced an unreliable state
        transition. Both items now use the constant-attribute path.

        Lazy-constructs the highlight item on first call; subsequent
        calls reuse it via setData (no item accumulation in the scene).
        Called by MainWindow at the end of `_load_stl_browser` and
        from `_on_fov_dragged` for live updates during drag.
        """
        full_heightmap = np.asarray(full_heightmap, dtype=np.float64)
        H_full, W_full = full_heightmap.shape
        H_fov, W_fov = fov_shape_pixels
        x_full_min, y_full_min = full_origin_mm
        fov_origin_x, fov_origin_y = fov_origin_mm

        # Pixel-index window into the full heightmap (same arithmetic
        # as MainWindow._extract_fov_slice).
        col = int(round((fov_origin_x - x_full_min) / pixel_size_mm))
        row = int(round((fov_origin_y - y_full_min) / pixel_size_mm))

        slice_z = np.zeros((H_fov, W_fov), dtype=np.float64)
        row_start = max(0, row)
        row_end = min(H_full, row + H_fov)
        col_start = max(0, col)
        col_end = min(W_full, col + W_fov)
        if row_start < row_end and col_start < col_end:
            out_row_start = row_start - row
            out_row_end = out_row_start + (row_end - row_start)
            out_col_start = col_start - col
            out_col_end = out_col_start + (col_end - col_start)
            slice_z[out_row_start:out_row_end, out_col_start:out_col_end] = (
                full_heightmap[row_start:row_end, col_start:col_end]
            )

        # Position the highlight in the part-bbox-centered plot frame
        # so it aligns with the existing whole-STL surface (which uses
        # centered coords). part_center = full_origin + W_full*ps/2.
        part_center_x = x_full_min + W_full * pixel_size_mm / 2.0
        part_center_y = y_full_min + H_full * pixel_size_mm / 2.0
        x = (
            fov_origin_x - part_center_x
            + np.arange(W_fov, dtype=np.float64) * pixel_size_mm
        )
        y = (
            fov_origin_y - part_center_y
            + np.arange(H_fov, dtype=np.float64) * pixel_size_mm
        )

        z_lifted = (slice_z + _FOV_HIGHLIGHT_Z_EPSILON_MM).T

        if self._whole_stl_highlight_item is None:
            self._whole_stl_highlight_item = gl.GLSurfacePlotItem(
                shader="shaded", smooth=False, drawEdges=False,
            )
            # Set the uniform color ONCE at construction. Color is fixed;
            # only geometry changes on subsequent updates. CRITICAL: do
            # NOT pass colors= to setData below — see method docstring.
            self._whole_stl_highlight_item.setColor(_FOV_HIGHLIGHT_COLOR_RGBA)
            self._whole_stl_view.addItem(self._whole_stl_highlight_item)
        self._whole_stl_highlight_item.setData(x=x, y=y, z=z_lifted)

    def clear_panel1_highlight(self) -> None:
        """Remove Panel 1's FOV highlight overlay from the scene.

        Called by MainWindow on small-STL loads — direct-path STLs
        don't have a meaningful FOV-selection context, so leaving a
        stale highlight from a prior Browser-mode load would be
        misleading. Resets `_whole_stl_highlight_item` to None;
        `has_panel1_highlight` reads False after.
        """
        if self._whole_stl_highlight_item is not None:
            self._whole_stl_view.removeItem(self._whole_stl_highlight_item)
            self._whole_stl_highlight_item = None
