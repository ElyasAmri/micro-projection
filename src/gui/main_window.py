"""main_window.py — Stage 4a task 3 GUI: surface controls wired to 3D preview.

QMainWindow with horizontal splitter:
- Left pane: surface selector + per-surface param sliders, geometry
  sliders, PSI step count, locked-hardware info panel.
- Right pane: SurfacePreview (3D heightmap render with viridis
  colormap).

Behavior wired in this commit (Stage 4a task 3)
-----------------------------------------------
- Surface QComboBox switches the QStackedWidget page (carried over
  from task 2).
- Surface QComboBox change ALSO triggers `_refresh_surface_preview`
  (new), which reads the current page's slider values and pushes a
  freshly-computed heightmap into the 3D view.
- Every surface-param slider (8 total across 4 pages) triggers
  `_refresh_surface_preview` via the new `LabeledFloatSlider.valueChanged`
  signal.

Still inert (deferred to task 4)
--------------------------------
Geometry sliders (theta_projector, theta_camera, projector_distance),
PSI step count, info-panel labels.

First math-module import: `src.test_surfaces`. The task-2 "no math
imports" constraint is deliberately lifted here — wiring those
generators into the GUI is the point of this task.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSpinBox,
    QSlider,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.gui.surface_preview import SurfacePreview
from src.test_surfaces import (
    make_flat,
    make_gaussian,
    make_sphere,
    make_step,
    make_tilt,
)


# Locked at Stage 4a launch defaults; revisit when info panel exposes
# hardware-derived values.
SURFACE_SHAPE: tuple[int, int] = (480, 640)
SURFACE_PIXEL_SIZE_MM: float = 0.1


# Locked hardware values for the info panel (PROJECT_CONTEXT Sec 2 +
# Projector_Geometry_Summary.docx). Placeholders for `p` and `a` are
# from notebook cell 1, rescaled to mm; revisit when real hardware is
# characterized.
HARDWARE_INFO_ROWS: list[tuple[str, str]] = [
    ("Camera", "FLIR Blackfly S BFS-U3-13Y3M-C"),
    ("Camera lens", "Edmund Optics #58-259, 0.09× telecentric"),
    ("Magnification (chapter)", "11.1"),
    ("Pixel pitch (object)", "0.053 mm"),
    ("FOV", "68 × 55 mm"),
    ("Projector", "Pico Genie Impact 2.0 Plus Elite"),
    ("Projector throw ratio", "1.2:1"),
    ("Grating period p (placeholder)", "2.0 mm"),
    ("DMD-to-lens a (placeholder)", "50 mm"),
]


class LabeledFloatSlider(QWidget):
    """QSlider + value label that exposes a float-valued range.

    QSlider is integer-only natively; this widget multiplies by a scale
    factor (derived from `step`) under the hood and exposes float
    `value()` / `set_value()` accessors. The value label updates
    automatically as the slider is dragged.

    Emits `valueChanged(float)` whenever the underlying slider moves.
    Task-3 callers (e.g., `MainWindow._refresh_surface_preview`)
    connect to this signal rather than the inner QSlider so the
    int<->float conversion stays encapsulated.
    """

    valueChanged = pyqtSignal(float)

    def __init__(
        self,
        label: str,
        vmin: float,
        vmax: float,
        default: float,
        step: float,
        suffix: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._step = step
        self._scale = round(1.0 / step)
        self._suffix = suffix
        # Number of decimals to display, derived from the step.
        self._decimals = max(0, len(f"{step:.10f}".rstrip("0").split(".")[-1]))

        self._name_label = QLabel(label)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(
            int(round(vmin * self._scale)), int(round(vmax * self._scale))
        )
        self._slider.setValue(int(round(default * self._scale)))

        self._value_label = QLabel()
        self._value_label.setMinimumWidth(70)
        self._value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._refresh_value_label(self._slider.value())
        self._slider.valueChanged.connect(self._refresh_value_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._name_label)
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._value_label)

    def _refresh_value_label(self, int_val: int) -> None:
        v = int_val / self._scale
        self._value_label.setText(f"{v:.{self._decimals}f}{self._suffix}")
        self.valueChanged.emit(v)

    def value(self) -> float:
        """Current slider value as a float."""
        return self._slider.value() / self._scale


class MainWindow(QMainWindow):
    """Top-level window. Horizontal splitter; left = controls, right = 3D."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Fringe Projection Digital Twin")
        self.resize(1280, 800)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_control_panel())
        splitter.addWidget(self._build_view_3d())
        splitter.setSizes([400, 880])
        self.setCentralWidget(splitter)

        self._wire_surface_refresh()
        # Initial render — pushes the default Gaussian into the view.
        self._refresh_surface_preview()

    # ------------------------------------------------------------------
    # Left pane — control panel
    # ------------------------------------------------------------------
    def _build_control_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        layout.addWidget(self._build_surface_group())
        layout.addWidget(self._build_geometry_group())
        layout.addWidget(self._build_psi_group())
        layout.addWidget(self._build_info_panel())
        layout.addStretch(1)

        return panel

    def _build_surface_group(self) -> QGroupBox:
        box = QGroupBox("Test Surface")
        layout = QVBoxLayout(box)

        self.surface_combo = QComboBox()
        self.surface_combo.addItems(["Flat", "Tilt", "Gaussian", "Step", "Sphere"])
        # Spec: Gaussian is the launch default.
        self.surface_combo.setCurrentText("Gaussian")
        layout.addWidget(self.surface_combo)

        self.surface_pages = QStackedWidget()
        self.surface_pages.addWidget(self._build_flat_page())
        self.surface_pages.addWidget(self._build_tilt_page())
        self.surface_pages.addWidget(self._build_gaussian_page())
        self.surface_pages.addWidget(self._build_step_page())
        self.surface_pages.addWidget(self._build_sphere_page())
        self.surface_pages.setCurrentIndex(self.surface_combo.currentIndex())
        layout.addWidget(self.surface_pages)

        # THE ONE WIRED BEHAVIOR (task 2 spec):
        self.surface_combo.currentIndexChanged.connect(
            self.surface_pages.setCurrentIndex
        )

        return box

    def _build_flat_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("No parameters"))
        return page

    def _build_tilt_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.tilt_slope_x = LabeledFloatSlider("slope_x", -1.0, 1.0, 0.0, 0.01)
        self.tilt_slope_y = LabeledFloatSlider("slope_y", -1.0, 1.0, 0.0, 0.01)
        layout.addWidget(self.tilt_slope_x)
        layout.addWidget(self.tilt_slope_y)
        return page

    def _build_gaussian_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.gaussian_amplitude = LabeledFloatSlider(
            "amplitude_mm", 0.0, 2.0, 0.5, 0.01
        )
        self.gaussian_sigma = LabeledFloatSlider("sigma_mm", 1.0, 30.0, 8.0, 0.1)
        layout.addWidget(self.gaussian_amplitude)
        layout.addWidget(self.gaussian_sigma)
        return page

    def _build_step_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.step_height = LabeledFloatSlider("height_mm", -2.0, 2.0, 0.5, 0.01)
        self.step_edge_x = LabeledFloatSlider("edge_x_mm", -30.0, 30.0, 0.0, 0.1)
        layout.addWidget(self.step_height)
        layout.addWidget(self.step_edge_x)
        return page

    def _build_sphere_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.sphere_cap_height = LabeledFloatSlider(
            "cap_height_mm", 0.01, 2.0, 0.5, 0.01
        )
        self.sphere_footprint = LabeledFloatSlider(
            "footprint_radius_mm", 1.0, 30.0, 20.0, 0.1
        )
        layout.addWidget(self.sphere_cap_height)
        layout.addWidget(self.sphere_footprint)
        return page

    def _build_geometry_group(self) -> QGroupBox:
        box = QGroupBox("Geometry")
        layout = QVBoxLayout(box)
        self.theta_projector = LabeledFloatSlider(
            "theta_projector_deg", -60.0, 60.0, 30.0, 1.0, suffix="°"
        )
        self.theta_camera = LabeledFloatSlider(
            "theta_camera_deg", -60.0, 60.0, 30.0, 1.0, suffix="°"
        )
        self.projector_distance = LabeledFloatSlider(
            "projector_distance_mm", 50.0, 200.0, 150.0, 1.0, suffix=" mm"
        )
        layout.addWidget(self.theta_projector)
        layout.addWidget(self.theta_camera)
        layout.addWidget(self.projector_distance)
        return box

    def _build_psi_group(self) -> QGroupBox:
        box = QGroupBox("Phase Shifting")
        layout = QHBoxLayout(box)
        layout.addWidget(QLabel("psi_steps"))
        self.psi_steps = QSpinBox()
        self.psi_steps.setRange(3, 8)
        self.psi_steps.setValue(4)
        layout.addWidget(self.psi_steps)
        layout.addStretch(1)
        return box

    def _build_info_panel(self) -> QGroupBox:
        box = QGroupBox("Locked Hardware Values")
        grid = QGridLayout(box)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        for row, (name, value) in enumerate(HARDWARE_INFO_ROWS):
            name_label = QLabel(name)
            name_label.setStyleSheet("color: #888;")
            value_label = QLabel(value)
            value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            grid.addWidget(name_label, row, 0)
            grid.addWidget(value_label, row, 1)
        return box

    # ------------------------------------------------------------------
    # Right pane — 3D surface preview
    # ------------------------------------------------------------------
    def _build_view_3d(self) -> QWidget:
        self.view_3d = SurfacePreview()
        return self.view_3d

    # ------------------------------------------------------------------
    # Surface refresh wiring (task 3)
    # ------------------------------------------------------------------
    def _wire_surface_refresh(self) -> None:
        """Connect dropdown + every surface slider to the refresh slot.

        Sliders on non-visible pages still emit signals when (rarely)
        their values change programmatically; the slot reads only the
        currently-visible page's values, so non-visible emissions are
        harmless no-ops.
        """
        self.surface_combo.currentIndexChanged.connect(
            self._refresh_surface_preview
        )
        for slider in self._all_surface_sliders():
            slider.valueChanged.connect(self._refresh_surface_preview)

    def _all_surface_sliders(self) -> list[LabeledFloatSlider]:
        return [
            self.tilt_slope_x,
            self.tilt_slope_y,
            self.gaussian_amplitude,
            self.gaussian_sigma,
            self.step_height,
            self.step_edge_x,
            self.sphere_cap_height,
            self.sphere_footprint,
        ]

    def _refresh_surface_preview(self, *_args: object) -> None:
        """Recompute the heightmap from current controls and push to view.

        Accepts any number of signal args (`currentIndexChanged(int)`
        and `valueChanged(float)` both connect here) and discards them.
        """
        heightmap = self._compute_current_heightmap()
        self.view_3d.update_heightmap(heightmap)

    def _compute_current_heightmap(self) -> np.ndarray:
        """Dispatch on current dropdown text -> matching make_* call."""
        name = self.surface_combo.currentText()
        shape = SURFACE_SHAPE
        ps = SURFACE_PIXEL_SIZE_MM

        if name == "Flat":
            return make_flat(shape, ps)
        if name == "Tilt":
            return make_tilt(
                shape, ps,
                slope_x=self.tilt_slope_x.value(),
                slope_y=self.tilt_slope_y.value(),
            )
        if name == "Gaussian":
            return make_gaussian(
                shape, ps,
                amplitude_mm=self.gaussian_amplitude.value(),
                sigma_mm=self.gaussian_sigma.value(),
            )
        if name == "Step":
            return make_step(
                shape, ps,
                height_mm=self.step_height.value(),
                edge_x_mm=self.step_edge_x.value(),
            )
        if name == "Sphere":
            return make_sphere(
                shape, ps,
                cap_height_mm=self.sphere_cap_height.value(),
                footprint_radius_mm=self.sphere_footprint.value(),
            )
        raise RuntimeError(f"unknown surface name: {name!r}")
