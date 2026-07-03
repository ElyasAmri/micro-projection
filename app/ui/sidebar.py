"""The left sidebar: controls for driving the simulation-backed rig.

Sim-agnostic -- it's handed the list of specimen names and just emits intent
(`project_requested`, `capture_requested`, `pipeline_requested`); the main
window wires those to the backend.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
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

        layout.addStretch(1)

    def selected_surface(self) -> str:
        return self.specimen.currentText()
