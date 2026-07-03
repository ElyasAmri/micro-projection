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
    noise_requested = Signal()     # estimate imaging noise + its error margin

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
