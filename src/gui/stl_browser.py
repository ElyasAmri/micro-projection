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
import pyqtgraph.opengl as gl
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
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
      - Top-left:    minimap (sub-task 5; QFrame placeholder for now)
      - Bottom-left: whole-STL 3D preview (orientation only)
      - Right:       windowed 3D preview (what the math measures)
    Placeholder shown otherwise.

    Whole-STL and windowed views are driven by `update_whole_stl` and
    `update_windowed_slice` respectively. The two methods stay separate
    so sub-task 5's drag handler can refresh Panel 3 on every mouse
    move without redoing Panel 1's larger mesh.
    """

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

        # Panel 2 (top-left): minimap placeholder — sub-task 5 fills.
        self._minimap_panel = _panel("Minimap (2D top-down, FOV rectangle)")

        # Panel 1 (bottom-left): whole-STL 3D preview.
        self._whole_stl_view = _new_3d_view(
            distance=300,  # placeholder; updated per part in update_whole_stl
            elevation=_WHOLE_STL_ELEVATION,
            azimuth=_WHOLE_STL_AZIMUTH,
        )
        self._whole_stl_item: Optional[gl.GLSurfacePlotItem] = None

        # Panel 3 (right): windowed 3D preview.
        self._windowed_view = _new_3d_view(**_WINDOWED_CAMERA)
        self._windowed_item: Optional[gl.GLSurfacePlotItem] = None

        inner.addWidget(self._minimap_panel)
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

    def show_panels(self) -> None:
        """Switch to the three-panel layout (Browser-mode STL active)."""
        self._stack.setCurrentIndex(1)

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
        pose is NOT reset between calls — sub-task 5's drag handler
        will call this on every mouse move and a jolting camera would
        be unusable. Initial pose comes from `__init__`.
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
