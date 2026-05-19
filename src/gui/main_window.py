"""main_window.py — Stage 4a task 4d GUI: pipeline stages viewer + view toggle.

QMainWindow with horizontal splitter:
- Left pane: surface selector + per-surface param sliders, geometry
  sliders, PSI step count, view-mode toggle, display-mode toggle,
  error-statistics panel (hidden until overlay is on), locked-
  hardware info panel.
- Right pane is a QStackedWidget with two pages:
    Page 0 (default): 3D scene = banner + SurfacePreview + colorbar
    Page 1:           StagesView (2x3 grid of 5 pipeline-stage images)

Stage 4a task 4d additions
--------------------------
- "View Mode" groupbox with two radio buttons (3D Scene / Pipeline
  Stages). Switches the right-pane QStackedWidget page.
- `run_pipeline(..., return_stages=True)` is called unconditionally
  in the refresh slot; intermediates feed the stages page when it's
  visible.

Stage 4a task 4c features (carried forward)
-------------------------------------------
- Degenerate-case warning banner: red QLabel atop the 3D scene page
  when |tan(θ_proj) + tan(θ_cam)| < 1e-3. (Banner sits on the 3D
  scene page only — it's visible when that page is current. The
  Stages page doesn't show it; users hit-test by switching back.)
- Error colorbar below view_3d on the 3D scene page.
- Z exaggeration 2× in SurfacePreview.
- Error stats auto-format to scientific notation when sub-precision.

Stage 4a task 4b features (carried forward)
-------------------------------------------
- "Display Mode" groupbox with `Show error overlay` checkbox.
- "Error Statistics" groupbox (hidden by default) showing mean, std,
  max abs, RMS of recovered - true error in mm.
- Toggling overlay re-routes coloring in `SurfacePreview`:
  off -> viridis on height (task 3 behavior);
  on  -> diverging blue-white-red on signed error, symmetric.
- Gaussian amplitude, Step height, Sphere cap-height slider maxes
  bumped to 100 mm so the user can drive recovery into clearly-
  visible regimes for the error-overlay demonstration.

Pre-existing behaviors carried forward
--------------------------------------
- Surface dropdown switches QStackedWidget pages (task 2) AND
  triggers `_refresh_surface_preview` (task 3).
- Surface sliders + theta_projector + theta_camera + psi_steps all
  trigger `_refresh_surface_preview`.
- Full pipeline runs in `_refresh_surface_preview` (task 4).

Still inert
-----------
- `projector_distance_mm` slider — affects coverage / lab view only,
  not the bias math (PROJECT_CONTEXT Sec 12).
- Info-panel labels — readonly display.

Hardcoded geometry constants
----------------------------
`_build_geometry()` uses notebook pixel-space values (M=1.0, p=40 px,
a=2000 px) that match the math layer's conventions; the info panel's
mm-space display values (M=11.1, p=2.0 mm, a=50 mm) are decorative
for now and will be reconciled when real hardware arrives in Stage
5/6. See commit 4/N message and PROJECT_CONTEXT Sec 12.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QRadioButton,
    QSpinBox,
    QSlider,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from geometry import HybridGeometry
from pipeline import run_pipeline
from src.gui.stages_view import StagesView
from src.gui.surface_preview import ErrorColorbar, SurfacePreview
from src.test_surfaces import (
    make_flat,
    make_gaussian,
)


# Below this threshold, |tan(theta_proj) + tan(theta_cam)| is treated
# as degenerate (the warning banner fires, the pipeline is short-
# circuited). 1e-3 is conservative — only the immediate neighborhood
# of the actual zero-crossing triggers.
DEGENERATE_TAN_SUM_THRESHOLD: float = 1e-3


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

    def set_value(self, v: float) -> None:
        """Programmatically set the slider value.

        Clamps to the slider's int range under the hood and emits
        `valueChanged(float)` if the new value differs from the
        current one. Used by smoke tests and any future automation.
        """
        self._slider.setValue(int(round(v * self._scale)))


class MainWindow(QMainWindow):
    """Top-level window. Horizontal splitter; left = controls, right = 3D."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Fringe Projection Digital Twin")
        self.resize(1280, 800)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_control_panel())
        splitter.addWidget(self._build_right_pane())
        splitter.setSizes([400, 880])
        self.setCentralWidget(splitter)

        self._wire_surface_refresh()
        # Initial render — pushes the default Gaussian into the view.
        self._refresh_surface_preview()
        # Stage 4b task 3: position the four hardware bodies at the
        # initial slider values. Without this, the bodies sit at
        # identity transforms (overlapping at the world origin) until
        # the first slider drag.
        self._on_pose_changed()

    # ------------------------------------------------------------------
    # Left pane — control panel
    # ------------------------------------------------------------------
    def _build_control_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        layout.addWidget(self._build_surface_group())
        layout.addWidget(self._build_geometry_group())
        layout.addWidget(self._build_psi_group())
        # Task 4d: view-mode toggle (3D scene vs pipeline stages).
        layout.addWidget(self._build_view_mode_group())
        # Task 4b additions: display-mode toggle + error stats panel.
        layout.addWidget(self._build_display_mode_group())
        layout.addWidget(self._build_error_stats_group())
        layout.addWidget(self._build_info_panel())
        layout.addStretch(1)

        return panel

    def _build_view_mode_group(self) -> QGroupBox:
        """`3D Scene` / `Pipeline Stages` radio toggle. Default 3D."""
        box = QGroupBox("View Mode")
        layout = QVBoxLayout(box)
        self.view_mode_3d = QRadioButton("3D Scene")
        self.view_mode_stages = QRadioButton("Pipeline Stages")
        self.view_mode_3d.setChecked(True)

        # QButtonGroup makes the two exclusive without parent-coupling.
        self._view_mode_group = QButtonGroup(self)
        self._view_mode_group.addButton(self.view_mode_3d)
        self._view_mode_group.addButton(self.view_mode_stages)

        layout.addWidget(self.view_mode_3d)
        layout.addWidget(self.view_mode_stages)
        return box

    def _build_display_mode_group(self) -> QGroupBox:
        """`Show error overlay` checkbox. Default unchecked."""
        box = QGroupBox("Display Mode")
        layout = QHBoxLayout(box)
        self.show_error_overlay = QCheckBox("Show error overlay")
        self.show_error_overlay.setChecked(False)
        layout.addWidget(self.show_error_overlay)
        layout.addStretch(1)
        return box

    def _build_error_stats_group(self) -> QGroupBox:
        """Error statistics readout. Hidden until overlay is enabled."""
        box = QGroupBox("Error Statistics")
        grid = QGridLayout(box)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        self.stat_mean = QLabel("—")
        self.stat_std = QLabel("—")
        self.stat_max_abs = QLabel("—")
        self.stat_rms = QLabel("—")

        rows = [
            ("Mean error:", self.stat_mean),
            ("Std error:", self.stat_std),
            ("Max abs error:", self.stat_max_abs),
            ("RMS error:", self.stat_rms),
        ]
        for row_idx, (name, value_label) in enumerate(rows):
            name_label = QLabel(name)
            name_label.setStyleSheet("color: #888;")
            value_label.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            grid.addWidget(name_label, row_idx, 0)
            grid.addWidget(value_label, row_idx, 1)

        box.setVisible(False)
        self.error_stats_group = box
        return box

    def _build_surface_group(self) -> QGroupBox:
        box = QGroupBox("Test Surface")
        layout = QVBoxLayout(box)

        self.surface_combo = QComboBox()
        # Stage 4c sub-task 1: dropdown reduced to Flat, Gaussian.
        # Page-add order below MUST match this label order (Flat=0,
        # Gaussian=1) — the currentIndexChanged -> setCurrentIndex wiring
        # is index-based while dispatch is currentText()-based.
        self.surface_combo.addItems(["Flat", "Gaussian"])
        # Spec: Gaussian is the launch default.
        self.surface_combo.setCurrentText("Gaussian")
        layout.addWidget(self.surface_combo)

        self.surface_pages = QStackedWidget()
        self.surface_pages.addWidget(self._build_flat_page())
        self.surface_pages.addWidget(self._build_gaussian_page())
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

    def _build_gaussian_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        # Range was 0..100 mm in task 4b; tightened to 0..55 mm in Stage
        # 4c sub-task 1 (the 55 mm vertical-FOV bound). Default 0.5 mm is
        # well under the cap, so it is unchanged.
        self.gaussian_amplitude = LabeledFloatSlider(
            "amplitude_mm", 0.0, 55.0, 0.5, 0.01
        )
        self.gaussian_sigma = LabeledFloatSlider("sigma_mm", 1.0, 30.0, 8.0, 0.1)
        layout.addWidget(self.gaussian_amplitude)
        layout.addWidget(self.gaussian_sigma)
        return page

    def _build_geometry_group(self) -> QGroupBox:
        box = QGroupBox("Geometry")
        layout = QVBoxLayout(box)
        # Range extended from ±60° to ±75° in Stage 4b task 4 to make
        # surface-clip cases reachable (a tilted lens-front disc only
        # reaches z=0 past ~67° at minimum WD); default ±30° unchanged.
        self.theta_projector = LabeledFloatSlider(
            "theta_projector_deg", -75.0, 75.0, 30.0, 1.0, suffix="°"
        )
        self.theta_camera = LabeledFloatSlider(
            "theta_camera_deg", -75.0, 75.0, 30.0, 1.0, suffix="°"
        )
        # Stage 4b task 3: distance sliders use the optics convention —
        # lens-front to surface (NOT body-center to surface). The
        # `compute_arm_transforms` math adds the body+lens offset
        # internally so the lens front lands at the slider value above
        # the surface.
        self.projector_distance = LabeledFloatSlider(
            "projector_throw_mm", 50.0, 200.0, 150.0, 1.0, suffix=" mm"
        )
        # `camera_distance` is the Edmund #58-259 working distance.
        # The lens stays in focus across 132-182 mm; the bias math
        # treats M as locked across this range (telecentric property),
        # so this slider only drives the lab-view scene, not the
        # pipeline. Default 157 mm = mid-range.
        self.camera_distance = LabeledFloatSlider(
            "camera_wd_mm", 132.0, 182.0, 157.0, 1.0, suffix=" mm"
        )
        layout.addWidget(self.theta_projector)
        layout.addWidget(self.theta_camera)
        layout.addWidget(self.projector_distance)
        layout.addWidget(self.camera_distance)
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
    # Right pane — QStackedWidget with two pages (3D scene / stages)
    # ------------------------------------------------------------------
    def _build_right_pane(self) -> QWidget:
        """Build the right pane as a QStackedWidget with two pages.

        Page 0 (default): the 3D scene (banner + SurfacePreview +
        error colorbar) — the right pane that existed prior to task 4d.
        Page 1: StagesView, the 2x3 grid of pipeline-stage images.

        The View Mode radio buttons in the left pane toggle the
        stack's current index.
        """
        page_3d = self._build_3d_scene_page()

        self.stages_view = StagesView()

        self.right_pane_stack = QStackedWidget()
        self.right_pane_stack.addWidget(page_3d)             # index 0
        self.right_pane_stack.addWidget(self.stages_view)    # index 1
        self.right_pane_stack.setCurrentIndex(0)

        return self.right_pane_stack

    def _build_3d_scene_page(self) -> QWidget:
        """Build the 3D scene page (banner + view_3d + colorbar).

        Returns the container; `self.view_3d` continues to refer to
        the SurfacePreview instance directly so existing callers
        (`update_heightmap`) work unchanged.
        """
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.warning_banner = self._build_warning_banner()
        layout.addWidget(self.warning_banner)

        # Stage 4b task 4: clip-detection banner. Sits directly below
        # the degenerate-λ_eq banner; the two are independent and can
        # show simultaneously (a degenerate pose can also be a clipping
        # pose). Same red visual treatment, top of the 3D scene page.
        self.clip_banner = self._build_clip_banner()
        layout.addWidget(self.clip_banner)

        self.view_3d = SurfacePreview()
        layout.addWidget(self.view_3d, 1)

        self.error_colorbar = ErrorColorbar()
        self.error_colorbar.setVisible(False)
        layout.addWidget(self.error_colorbar)

        return container

    def _build_warning_banner(self) -> QLabel:
        """Degenerate-geometry warning banner. Hidden until needed.

        The banner shows the textbook form of Eq. 2-51:
            λ_eq = Mp / (tan θ_proj + tan θ_cam)
        The code's internal `equivalent_wavelength()` returns
        λ_textbook / (2π) (the 2π from Eq. 2-51's `× ψ/(2π)` has been
        pre-folded in). The banner mirrors the textbook so users
        matching banner text to the chapter PDF see the same
        equation. See geometry.py for the implementation convention.
        """
        banner = QLabel()
        banner.setTextFormat(Qt.TextFormat.RichText)
        banner.setText(
            "<b>⚠ No height sensitivity</b><br/>"
            "λ_eq = Mp / (tan θ_proj + tan θ_cam) → ∞<br/>"
            "Denominator: tan θ_proj + tan θ_cam ≈ 0<br/>"
            "Adjust either angle to restore triangulation. (Eq. 2-51)"
        )
        banner.setStyleSheet(
            "background-color: rgba(180, 30, 30, 200);"
            " color: white;"
            " padding: 8px;"
            " border: 2px solid rgb(220, 60, 60);"
            " font-family: monospace;"
            " font-size: 11px;"
        )
        banner.setVisible(False)
        return banner

    def _build_clip_banner(self) -> QLabel:
        """Clip-detection warning banner. Hidden until a clip fires.

        Unlike the degenerate-λ_eq banner (which short-circuits the
        pipeline because λ_eq is infinite), clip warnings are advisory:
        the math keeps running, the rig is just not physically
        buildable. Text is set live by `_update_clip_warning` from the
        ClipState message list (one line per triggered check).
        """
        banner = QLabel()
        banner.setTextFormat(Qt.TextFormat.RichText)
        banner.setStyleSheet(
            "background-color: rgba(180, 30, 30, 200);"
            " color: white;"
            " padding: 8px;"
            " border: 2px solid rgb(220, 60, 60);"
            " font-family: monospace;"
            " font-size: 11px;"
        )
        banner.setVisible(False)
        return banner

    def _update_clip_warning(self, messages: list[str]) -> None:
        """Show/hide the clip banner from a ClipState message list.

        Empty list -> hide. Non-empty -> show all messages, one per
        line, prefixed with a warning glyph on the first line.
        """
        if not messages:
            self.clip_banner.setVisible(False)
            return
        body = "<br/>".join(messages)
        self.clip_banner.setText(f"<b>⚠ Physical clip</b><br/>{body}")
        self.clip_banner.setVisible(True)

    # ------------------------------------------------------------------
    # Surface refresh wiring (task 3)
    # ------------------------------------------------------------------
    def _wire_surface_refresh(self) -> None:
        """Connect every control whose change should re-run the pipeline
        and / or update the hardware-body poses in the 3D scene.

        Two slots fan out from the geometry sliders now (Stage 4b task 3):

        - `_refresh_surface_preview` (existing, expensive — full math
          pipeline). Connected for theta sliders only; the distance
          sliders don't drive the bias math (M is locked by the
          telecentric camera lens, and `a` is fixed inside the
          projector — PROJECT_CONTEXT Sec 12).

        - `_on_pose_changed` (new, cheap — three matrix multiplies and
          four `setTransform` calls). Connected for all four pose
          sliders: both theta sliders, both distance sliders. Drives
          the hardware-body positions / orientations in the 3D scene
          in lockstep with slider drags.

        Sliders on non-visible surface pages still emit signals when
        (rarely) their values change programmatically; the slot reads
        only the currently-visible page's values, so non-visible
        emissions are harmless no-ops.
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

        # Stage 4b task 3: pose sliders drive the hardware-body scene.
        # Theta sliders ALREADY trigger pipeline reruns above; this adds
        # the (cheap) pose-update path on top. Distance sliders trigger
        # ONLY the pose update — they don't enter the math layer.
        self.theta_projector.valueChanged.connect(self._on_pose_changed)
        self.theta_camera.valueChanged.connect(self._on_pose_changed)
        self.projector_distance.valueChanged.connect(self._on_pose_changed)
        self.camera_distance.valueChanged.connect(self._on_pose_changed)

        # Stage 4a task 4b addition: error overlay toggle.
        self.show_error_overlay.toggled.connect(self._on_overlay_toggled)

        # Stage 4a task 4d addition: view-mode radio toggle.
        # Connecting just view_mode_3d.toggled is enough — it fires on
        # both check and uncheck thanks to the QButtonGroup exclusivity.
        self.view_mode_3d.toggled.connect(self._on_view_mode_changed)

    def _all_surface_sliders(self) -> list[LabeledFloatSlider]:
        return [
            self.gaussian_amplitude,
            self.gaussian_sigma,
        ]

    def _refresh_surface_preview(self, *_args: object) -> None:
        """Recompute heightmap, run the pipeline, push to current view.

        Accepts any number of signal args (`currentIndexChanged(int)`,
        `valueChanged(float)` from LabeledFloatSlider, and
        `valueChanged(int)` from QSpinBox all connect here) and
        discards them.

        Degenerate short-circuit (task 4c): if
        |tan(θ_proj) + tan(θ_cam)| < DEGENERATE_TAN_SUM_THRESHOLD,
        the pipeline is NOT run (recovery would be NaN); the warning
        banner is shown, the colorbar is hidden, and neither view
        updates (both keep their last good frame).

        Otherwise:
        - In stages view (task 4d): push all five intermediate arrays
          into StagesView panels. The 3D scene's view_3d + colorbar
          stay frozen on their last good state; colorbar is hidden
          since it's not visible anyway.
        - In 3D scene view: branches on `self.show_error_overlay`:
          * OFF: render recovered surface with viridis-on-height
            (task 3 default). Colorbar hidden.
          * ON:  render recovered surface colored by signed error
            (recovered - heightmap) with the diverging colormap,
            update the error-statistics labels, and show the colorbar.
        """
        heightmap = self._compute_current_heightmap()
        geometry = self._build_geometry()

        # Degenerate-geometry check (task 4c).
        tan_sum = abs(
            math.tan(geometry.theta_projector)
            + math.tan(geometry.theta_camera)
        )
        if tan_sum < DEGENERATE_TAN_SUM_THRESHOLD:
            self.warning_banner.setVisible(True)
            self.error_colorbar.setVisible(False)
            return
        self.warning_banner.setVisible(False)

        # Always request stages: the dict is cheap (references, not
        # copies) and the stages page may be visible.
        recovered, stages = run_pipeline(
            heightmap=heightmap,
            geometry=geometry,
            n_psi_steps=self.psi_steps.value(),
            return_stages=True,
        )

        if self.view_mode_stages.isChecked():
            # Stages page is current — push to it. Hide colorbar
            # (it belongs to the 3D scene page anyway).
            self.stages_view.update_stages(
                ground_truth=stages["ground_truth"],
                fringe_frame=stages["fringe_frame"],
                wrapped_phase=stages["wrapped_phase"],
                unwrapped_phase=stages["unwrapped_phase"],
                recovered=recovered,
            )
            self.error_colorbar.setVisible(False)
            return

        # 3D scene page is current.
        if self.show_error_overlay.isChecked():
            error = recovered - heightmap
            self.view_3d.update_heightmap(recovered, error_mm=error)
            abs_max = self._update_error_stats(error)
            self.error_colorbar.set_range(abs_max)
            self.error_colorbar.setVisible(True)
        else:
            self.view_3d.update_heightmap(recovered)
            self.error_colorbar.setVisible(False)

    def _on_overlay_toggled(self, checked: bool) -> None:
        """Show/hide the stats panel and re-render."""
        self.error_stats_group.setVisible(checked)
        self._refresh_surface_preview()

    def _on_pose_changed(self, *_args: object) -> None:
        """Push fresh hardware-body poses into the 3D scene.

        Stage 4b task 3 slot. Cheap path (3 matrix multiplies + 4
        `setTransform` calls). Fires on every pose-slider drag,
        independent of the math-pipeline rerun.

        Accepts variadic args so it can be connected directly to
        `valueChanged(float)`-emitting sliders without an adapter.

        The returned ClipState drives the clip-warning banner. This is
        independent of the degenerate-λ_eq banner (which is owned by
        `_refresh_surface_preview`); both can be visible at once.
        """
        clip_state = self.view_3d.update_hardware_pose(
            theta_camera_deg=self.theta_camera.value(),
            theta_projector_deg=self.theta_projector.value(),
            projector_distance_mm=self.projector_distance.value(),
            camera_distance_mm=self.camera_distance.value(),
            heightmap_mm=self._compute_current_heightmap(),
            surface_pixel_size_mm=SURFACE_PIXEL_SIZE_MM,
        )
        self._update_clip_warning(clip_state.messages)

    def _on_view_mode_changed(self, _checked: bool) -> None:
        """Switch the right-pane stack page and refresh.

        `toggled` fires on both check and uncheck of view_mode_3d.
        We dispatch on whichever button is checked rather than
        on the signal's boolean argument.
        """
        if self.view_mode_3d.isChecked():
            self.right_pane_stack.setCurrentIndex(0)
        else:
            self.right_pane_stack.setCurrentIndex(1)
        # Newly-visible page may have stale data if sliders moved
        # while it was hidden.
        self._refresh_surface_preview()

    def _update_error_stats(self, error: np.ndarray) -> float:
        """Refresh the four QLabels and return abs_max for the colorbar.

        Uses NaN-safe reductions so the degenerate λ_eq case (error
        all NaN) shows `—` instead of crashing — though task 4c's
        degenerate short-circuit already prevents this method from
        being called in that case.

        Returns
        -------
        float
            np.nanmax(np.abs(error)), or 0.0 if all-NaN. The
            colorbar uses this to set its symmetric range.
        """
        if np.all(np.isnan(error)):
            for label in (
                self.stat_mean, self.stat_std,
                self.stat_max_abs, self.stat_rms,
            ):
                label.setText("—")
            return 0.0

        mean = float(np.nanmean(error))
        std = float(np.nanstd(error))
        max_abs = float(np.nanmax(np.abs(error)))
        rms = float(np.sqrt(np.nanmean(error ** 2)))

        self.stat_mean.setText(self._format_error_value(mean))
        self.stat_std.setText(self._format_error_value(std))
        self.stat_max_abs.setText(self._format_error_value(max_abs))
        self.stat_rms.setText(self._format_error_value(rms))
        return max_abs if np.isfinite(max_abs) else 0.0

    @staticmethod
    def _format_error_value(value: float) -> str:
        """Auto-format: scientific notation for sub-precision values.

        Pre-task-4c the format was always `{value:.5f} mm`, which
        rounded machine-precision residuals (~1e-13) to `0.00000`.
        Sci notation for |value| < 1e-4 (and non-zero) makes those
        residuals readable.
        """
        if abs(value) < 1e-4 and value != 0.0:
            return f"{value:.3e} mm"
        return f"{value:.5f} mm"

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
        if name == "Gaussian":
            return make_gaussian(
                shape, ps,
                amplitude_mm=self.gaussian_amplitude.value(),
                sigma_mm=self.gaussian_sigma.value(),
            )
        raise RuntimeError(f"unknown surface name: {name!r}")
