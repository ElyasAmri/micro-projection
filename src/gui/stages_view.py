"""stages_view.py — 2x3 grid of 5 pipeline-stage panels.

Renders all intermediate arrays from `pipeline.run_pipeline(...,
return_stages=True)` as 2D camera-view images alongside the GUI's
main 3D scene. The user toggles between the two views via radio
buttons in `main_window`.

Grid layout (2 rows x 3 cols, last cell empty):

    [Ground truth     ] [Projected fringes] [Wrapped phase]
    [Unwrapped phase  ] [Recovered height ] [empty        ]

Each non-empty cell stacks:
    QLabel(title, bold, centered)
    pg.ImageView (no histogram side-panel — too narrow at 3-column width)
    QLabel(equation, monospace, word-wrap)

Performance note
----------------
Each `update_stages()` pushes 5 ImageViews at the heightmap's native
resolution (480x640 by default in the GUI). At 60 fps that's 5x
307k vertices through OpenGL per tick; OK on modern GPUs. If lag
shows up, downsample inside update_stages — the public signature
stays the same.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


# Module-level cached colormaps so panels share single instances.
# pyqtgraph 0.14.0 does not bundle 'hsv' or 'gray', so we build the
# grayscale one manually and pick CET-C1 (perceptually-uniform cyclic)
# as the wrapped-phase cmap.
_CMAP_VIRIDIS = pg.colormap.get("viridis")
_CMAP_CYCLIC = pg.colormap.get("CET-C1")
_CMAP_GRAY = pg.ColorMap(
    pos=[0.0, 1.0],
    color=[(0, 0, 0, 255), (255, 255, 255, 255)],
)


def _build_panel(
    title: str,
    equation: str,
    cmap: pg.ColorMap,
) -> tuple[QWidget, pg.ImageView]:
    """Construct one stage panel. Returns (container_widget, image_view).

    Container is a QVBoxLayout: title (bold) on top, ImageView middle,
    equation (monospace, word-wrapped) at the bottom.
    """
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(2, 2, 2, 2)
    layout.setSpacing(2)

    title_label = QLabel(title)
    title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title_label.setStyleSheet("font-weight: bold;")
    layout.addWidget(title_label)

    image_view = pg.ImageView()
    image_view.setColorMap(cmap)
    # Hide histogram side-panel: at the right pane's ~880 px width
    # divided across 3 columns, the histogram eats ~80-100 px each
    # and crowds the actual image. Hide its title-row buttons too.
    image_view.ui.histogram.hide()
    image_view.ui.roiBtn.hide()
    image_view.ui.menuBtn.hide()
    layout.addWidget(image_view, 1)

    eq_label = QLabel(equation)
    eq_label.setStyleSheet(
        "font-family: monospace; font-size: 9pt; color: #ccc;"
    )
    eq_label.setWordWrap(True)
    eq_label.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
    )
    layout.addWidget(eq_label)

    return container, image_view


class StagesView(QWidget):
    """2x3 grid of 5 pipeline stages, populated by update_stages().

    Attributes (each is a pyqtgraph.ImageView):
        iv_ground_truth
        iv_fringe_frame
        iv_wrapped_phase
        iv_unwrapped_phase
        iv_recovered
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        grid = QGridLayout(self)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(6)

        # Row 0
        ground_widget, self.iv_ground_truth = _build_panel(
            title="Ground truth",
            equation="h(x, y) — input from sliders",
            cmap=_CMAP_VIRIDIS,
        )
        grid.addWidget(ground_widget, 0, 0)

        fringe_widget, self.iv_fringe_frame = _build_panel(
            title="Projected fringes (camera view)",
            equation="I(x, y) = A + B·cos[2π·x/p + h/λ_eq + δ_k]",
            cmap=_CMAP_GRAY,
        )
        grid.addWidget(fringe_widget, 0, 1)

        wrapped_widget, self.iv_wrapped_phase = _build_panel(
            title="Wrapped phase",
            equation="ψ_wrapped = arctan2(-Σ I·sin δ, Σ I·cos δ)",
            cmap=_CMAP_CYCLIC,
        )
        grid.addWidget(wrapped_widget, 0, 2)

        # Row 1
        unwrapped_widget, self.iv_unwrapped_phase = _build_panel(
            title="Unwrapped phase",
            equation="ψ_unwrapped — 2D unwrap (np.unwrap rows then cols)",
            cmap=_CMAP_VIRIDIS,
        )
        grid.addWidget(unwrapped_widget, 1, 0)

        recovered_widget, self.iv_recovered = _build_panel(
            title="Recovered height",
            equation="h = λ_eq · (ψ_unwrapped − ψ_cal) / (2π)   (Eq. 2-51)",
            cmap=_CMAP_VIRIDIS,
        )
        grid.addWidget(recovered_widget, 1, 1)

        # Cell (1, 2) intentionally empty.
        grid.addWidget(QWidget(), 1, 2)

        # Make all cells stretch evenly.
        for c in range(3):
            grid.setColumnStretch(c, 1)
        for r in range(2):
            grid.setRowStretch(r, 1)

    def update_stages(
        self,
        ground_truth: np.ndarray,
        fringe_frame: np.ndarray,
        wrapped_phase: np.ndarray,
        unwrapped_phase: np.ndarray,
        recovered: np.ndarray,
    ) -> None:
        """Push the five (H, W) arrays into their respective ImageViews.

        `autoLevels=True` per call so each panel's color range adapts
        to its own data (different units per panel: mm, intensity,
        radians).
        """
        self.iv_ground_truth.setImage(ground_truth, autoLevels=True)
        self.iv_fringe_frame.setImage(fringe_frame, autoLevels=True)
        self.iv_wrapped_phase.setImage(wrapped_phase, autoLevels=True)
        self.iv_unwrapped_phase.setImage(unwrapped_phase, autoLevels=True)
        self.iv_recovered.setImage(recovered, autoLevels=True)
