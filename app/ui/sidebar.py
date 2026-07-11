"""The left sidebar: controls for driving the simulation-backed rig.

Sim-agnostic -- it's handed the list of specimen names and just emits intent
(`project_requested`, `capture_requested`, `pipeline_requested`); the main
window wires those to the backend.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class Sidebar(QWidget):
    """Left control panel. Emits an intent signal per button press."""

    project_requested = Signal()   # show the projected fringe pattern
    capture_requested = Signal()   # single capture of the fringe on the surface
    pipeline_requested = Signal()  # full project -> capture -> reconstruct
    multifreq_requested = Signal() # coarse->fine ladder capture + unwrapping
    noise_requested = Signal()     # estimate imaging noise + its error margin
    rig_requested = Signal()       # render the annotated rig overview (Rig tab)
    camera_settings_requested = Signal()  # open the camera settings dialog
    patterns_requested = Signal()  # open the pattern library dialog
    calibrate_requested = Signal()  # measure the camera angle (box + fringes)
    aim_requested = Signal(bool)    # toggle the camera-aim measurement loop
    camera_noise_requested = Signal()  # camera temporal-noise qualification

    def __init__(self, surfaces: list[str], header: str = "Simulation",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.setMinimumWidth(230)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)

        header_label = QLabel(header)  # the active backend: "Simulation" / "Hardware"
        header_label.setProperty("role", "sectionHeader")
        layout.addWidget(header_label)

        specimen_label = QLabel("Specimen")
        specimen_label.setObjectName("fieldLabel")
        layout.addWidget(specimen_label)

        self.specimen = QComboBox()
        self.specimen.setObjectName("specimenSelect")
        self.specimen.addItems(surfaces)
        layout.addWidget(self.specimen)

        actions = QLabel("Actions")
        actions.setProperty("role", "sectionHeader")
        layout.addWidget(actions)

        self.project_button = QPushButton("Project Fringe")
        self.project_button.setObjectName("projectButton")
        self.project_button.clicked.connect(lambda: self.project_requested.emit())
        layout.addWidget(self.project_button)

        self.patterns_button = QPushButton("Project Pattern...")
        self.patterns_button.setObjectName("patternsButton")
        self.patterns_button.setToolTip(
            "Open the pattern library: alignment/focus/linearity patterns "
            "(grid, checkerboard, solids, ramp, ...) or any image file, "
            "projected through the same path as the fringe."
        )
        self.patterns_button.clicked.connect(lambda: self.patterns_requested.emit())
        layout.addWidget(self.patterns_button)

        self.capture_button = QPushButton("Capture")
        self.capture_button.setObjectName("captureButton")
        self.capture_button.setEnabled(bool(surfaces))
        self.capture_button.clicked.connect(lambda: self.capture_requested.emit())
        layout.addWidget(self.capture_button)

        self.pipeline_button = QPushButton("Run Pipeline")
        self.pipeline_button.setObjectName("pipelineButton")
        self.pipeline_button.setProperty("variant", "primary")
        self.pipeline_button.setEnabled(bool(surfaces))
        self.pipeline_button.clicked.connect(lambda: self.pipeline_requested.emit())
        layout.addWidget(self.pipeline_button)

        self.multifreq_button = QPushButton("Run Multi-Freq")
        self.multifreq_button.setObjectName("multifreqButton")
        self.multifreq_button.setProperty("variant", "primary")
        self.multifreq_button.setEnabled(bool(surfaces))
        self.multifreq_button.setToolTip(
            "Capture a coarse->fine ladder of fringe frequencies and unwrap them "
            "together: the coarse rung fixes the range, the fine rung the vertical "
            "resolution (~10x sharper). The basis for measuring roughness."
        )
        self.multifreq_button.clicked.connect(lambda: self.multifreq_requested.emit())
        layout.addWidget(self.multifreq_button)

        self.rig_button = QPushButton("Render Rig View")
        self.rig_button.setObjectName("rigButton")
        self.rig_button.setToolTip(
            "Render an annotated Blender overview of the rig -- the PRO4500 "
            "projector, the tilted FLIR + GoldTL telecentric camera in its "
            "mounting clamp, and the fringe-lit specimen on its 125 mm "
            "Z-stage, mounted on the vertical breadboard bench, all modeled "
            "to vendor dimensions -- into the Rig tab. "
            "Drag on the Rig view to orbit it (the gizmo tracks the drag; "
            "the render fires on release), scroll to zoom."
        )
        self.rig_button.clicked.connect(lambda: self.rig_requested.emit())
        layout.addWidget(self.rig_button)

        # -- Camera: the device configuration the next capture runs with -----
        camera_header = QLabel("Camera")
        camera_header.setProperty("role", "sectionHeader")
        layout.addWidget(camera_header)

        self.camera_settings_button = QPushButton("Camera Settings...")
        self.camera_settings_button.setObjectName("cameraSettingsButton")
        self.camera_settings_button.setToolTip(
            "Configure the FLIR camera: exposure, gain, gamma, black level. "
            "Settings persist across sessions and are applied when the next "
            "capture opens the camera."
        )
        self.camera_settings_button.clicked.connect(
            lambda: self.camera_settings_requested.emit())
        layout.addWidget(self.camera_settings_button)

        # -- Calibration: measure the rig geometry with the projector + camera --
        calibration_header = QLabel("Calibration")
        calibration_header.setProperty("role", "sectionHeader")
        layout.addWidget(calibration_header)

        self.calibrate_button = QPushButton("Calibrate Camera Angle")
        self.calibrate_button.setObjectName("calibrateButton")
        self.calibrate_button.setEnabled(bool(surfaces))
        self.calibrate_button.setToolTip(
            "Measure the camera's viewing angle using the projector: one "
            "projected square (box-aspect estimate) plus vertical and "
            "horizontal phase-shifted fringes (phase-gradient estimate). "
            "Both angles and their difference go to the console; needs the "
            "hardware backend."
        )
        self.calibrate_button.clicked.connect(lambda: self.calibrate_requested.emit())
        layout.addWidget(self.calibrate_button)

        self.aim_button = QPushButton("Aim Camera")
        self.aim_button.setObjectName("aimButton")
        self.aim_button.setCheckable(True)
        self.aim_button.setEnabled(bool(surfaces))
        self.aim_button.setToolTip(
            "Guided aiming loop: projects a marker at the field center and "
            "measures its offset from the camera center every couple of "
            "seconds. Adjust the mount until the offset reads near zero, "
            "then click again to stop. Needs the hardware backend."
        )
        self.aim_button.toggled.connect(self.aim_requested)
        layout.addWidget(self.aim_button)

        self.camera_noise_button = QPushButton("Camera Noise Test")
        self.camera_noise_button.setObjectName("cameraNoiseButton")
        self.camera_noise_button.setEnabled(bool(surfaces))
        self.camera_noise_button.setToolTip(
            "Camera qualification: project a static flat field, grab many "
            "frames, and check the per-pixel temporal noise against pass/fail "
            "thresholds (report + heatmap). Distinct from Estimate Noise, "
            "which analyses reconstruction error. Needs the hardware backend."
        )
        self.camera_noise_button.clicked.connect(
            lambda: self.camera_noise_requested.emit())
        layout.addWidget(self.camera_noise_button)

        # -- Error analysis: noise + auto-exposure swing, and the margin they --
        # impose on the reconstruction.
        error_header = QLabel("Error Analysis")
        error_header.setProperty("role", "sectionHeader")
        layout.addWidget(error_header)

        noise_label = QLabel("Injected noise (DN)")
        noise_label.setObjectName("fieldLabel")
        layout.addWidget(noise_label)

        self.noise_level = QDoubleSpinBox()
        self.noise_level.setObjectName("noiseLevel")
        self.noise_level.setRange(0.0, 30.0)
        self.noise_level.setSingleStep(0.5)
        self.noise_level.setDecimals(1)
        self.noise_level.setValue(5.0)
        self.noise_level.setToolTip(
            "Known random noise to inject into a simulated specimen, to check "
            "the estimator. Ignored for a real capture (its noise is measured)."
        )
        layout.addWidget(self.noise_level)

        swing_label = QLabel("Exposure swing (%)")
        swing_label.setObjectName("fieldLabel")
        layout.addWidget(swing_label)

        self.swing_level = QDoubleSpinBox()
        self.swing_level.setObjectName("swingLevel")
        self.swing_level.setRange(0.0, 20.0)
        self.swing_level.setSingleStep(0.5)
        self.swing_level.setDecimals(1)
        self.swing_level.setValue(0.0)
        self.swing_level.setToolTip(
            "Known per-frame brightness swing to inject (the auto-exposure "
            "effect), to show its cost and how much correcting it recovers. "
            "Ignored for a real capture (its swing is measured)."
        )
        layout.addWidget(self.swing_level)

        self.noise_button = QPushButton("Analyze Errors")
        self.noise_button.setObjectName("noiseButton")
        self.noise_button.setEnabled(bool(surfaces))
        self.noise_button.clicked.connect(lambda: self.noise_requested.emit())
        layout.addWidget(self.noise_button)

        layout.addStretch(1)

    def selected_surface(self) -> str:
        return self.specimen.currentText()

    def injected_noise_dn(self) -> float:
        """The random noise level (in 8-bit DN) to inject in a simulated run."""
        return self.noise_level.value()

    def exposure_swing_pct(self) -> float:
        """The per-frame brightness swing (percent) to inject in a simulated run."""
        return self.swing_level.value()
