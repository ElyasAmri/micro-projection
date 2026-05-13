"""main_window.py — Stage 4a task 2 GUI skeleton (layout only).

QMainWindow with horizontal splitter:
- Left pane: surface selector + per-surface param sliders, geometry
  sliders, PSI step count, locked-hardware info panel.
- Right pane: pyqtgraph OpenGL view with a placeholder grid.

Behavior wired in this commit
-----------------------------
Exactly ONE: the surface QComboBox switches the QStackedWidget page so
the user can see each surface type's param sliders. Every other widget
(all sliders, the PSI spinbox, the info panel, the 3D view) is inert;
they emit signals that nothing listens to.

No math-layer imports yet — that's task 3.
"""
from __future__ import annotations

from typing import Optional

import pyqtgraph.opengl as gl
from PyQt6.QtCore import Qt
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
    """

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
    # Right pane — 3D view placeholder
    # ------------------------------------------------------------------
    def _build_view_3d(self) -> QWidget:
        view = gl.GLViewWidget()
        view.setBackgroundColor((30, 30, 30))
        view.setCameraPosition(distance=80)
        grid_item = gl.GLGridItem()
        grid_item.setSize(x=100, y=100)
        grid_item.setSpacing(x=5, y=5)
        view.addItem(grid_item)
        self.view_3d = view
        return view
