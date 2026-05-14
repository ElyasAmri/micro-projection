"""main_window.py — Stage 4a task 4 GUI: full pipeline integration.

QMainWindow with horizontal splitter:
- Left pane: surface selector + per-surface param sliders, geometry
  sliders, PSI step count, locked-hardware info panel.
- Right pane: SurfacePreview rendering the RECOVERED height (the full
  forward + inverse fringe-projection pipeline runs on every slider
  change).

Behavior wired in this commit (Stage 4a task 4)
-----------------------------------------------
- Surface QComboBox switches the QStackedWidget page (carried over
  from task 2) AND triggers `_refresh_surface_preview` (task 3).
- Every surface-param slider (8 total) triggers `_refresh_surface_preview`.
- NEW: `theta_projector_deg`, `theta_camera_deg`, and `psi_steps`
  now also trigger `_refresh_surface_preview`.
- The refresh slot now runs the full pipeline (test_surfaces -> geometry
  -> synth -> phase-shift -> unwrap -> calibrate -> reconstruct) and
  pushes the RECOVERED heightmap into the 3D view.

Still inert
-----------
- `projector_distance_mm` slider — affects coverage / lab view only,
  not the bias math (PROJECT_CONTEXT Sec 12).
- Info-panel labels — readonly display.

Hardcoded geometry constants
----------------------------
M=11.1, p=2.0, a=50.0 in `_build_geometry()` match the info panel's
locked values from task 2. These have a known dimensional mismatch
with the math layer (which uses pixel-index X internally and modern-
convention M); see commit 4/N message and PROJECT_CONTEXT Sec 12.
They will move to a config object when the info panel exposes
hardware-derived values.
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

from geometry import HybridGeometry
from pipeline import run_pipeline
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

# Hardcoded geometry constants in NOTEBOOK PIXEL-SPACE UNITS.
# The math layer (synthetic_fringes.project's X = np.arange(W),
# geometry.py's M_modern convention) was written in pixel-space, so
# these values match the notebook/regression-fixture conventions —
# NOT the info panel's mm-space display values (M=11.1, p=2.0 mm,
# a=50 mm). Unit reconciliation between info panel and math layer
# is a deferred Stage 5/6 concern; when real hardware arrives, these
# constants will be derived from the info panel + the camera's
# object-space pixel pitch. See module docstring.
GEOMETRY_M: float = 1.0
GEOMETRY_P_PX: float = 40.0
GEOMETRY_A_PX: float = 2000.0


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
        """Connect every control whose change should re-run the pipeline.

        Sliders on non-visible surface pages still emit signals when
        (rarely) their values change programmatically; the slot reads
        only the currently-visible page's values, so non-visible
        emissions are harmless no-ops.

        Note: `projector_distance` is intentionally NOT connected — it
        affects coverage / lab-view geometry only, not the bias math
        (PROJECT_CONTEXT Sec 12). Wiring it would trigger pointless
        pipeline re-runs.
        """
        self.surface_combo.currentIndexChanged.connect(
            self._refresh_surface_preview
        )
        for slider in self._all_surface_sliders():
            slider.valueChanged.connect(self._refresh_surface_preview)

        # Stage 4a task 4 additions: geometry sliders + PSI step count.
        self.theta_projector.valueChanged.connect(self._refresh_surface_preview)
        self.theta_camera.valueChanged.connect(self._refresh_surface_preview)
        self.psi_steps.valueChanged.connect(self._refresh_surface_preview)

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
        """Recompute heightmap, run the pipeline, push recovered to view.

        Accepts any number of signal args (`currentIndexChanged(int)`,
        `valueChanged(float)` from LabeledFloatSlider, and
        `valueChanged(int)` from QSpinBox all connect here) and
        discards them.
        """
        heightmap = self._compute_current_heightmap()
        geometry = self._build_geometry()
        recovered = run_pipeline(
            heightmap=heightmap,
            geometry=geometry,
            n_psi_steps=self.psi_steps.value(),
        )
        self.view_3d.update_heightmap(recovered)

    def _build_geometry(self) -> HybridGeometry:
        """Construct a HybridGeometry from current slider values.

        M, p, a are hardcoded notebook pixel-space values (M=1.0,
        p=40 px, a=2000 px) that match the math layer's expected
        conventions. The info panel's display values (M=11.1
        chapter, p=2.0 mm, a=50 mm) are decorative for now and
        will be reconciled with the math layer when real hardware
        arrives in Stage 5/6. Only the two arm-tilt angles come
        from sliders.
        """
        return HybridGeometry(
            M=GEOMETRY_M,
            p=GEOMETRY_P_PX,
            a=GEOMETRY_A_PX,
            theta_projector=float(np.deg2rad(self.theta_projector.value())),
            theta_camera=float(np.deg2rad(self.theta_camera.value())),
        )

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
