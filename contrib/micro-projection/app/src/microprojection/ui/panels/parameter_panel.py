from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ParameterPanel(QWidget):
    """Controls for pipeline parameters."""

    parameters_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        # -- Capture group --
        capture_group = QGroupBox("Capture")
        capture_layout = QFormLayout(capture_group)

        self._n_steps = QSpinBox()
        self._n_steps.setRange(3, 16)
        self._n_steps.setValue(4)
        capture_layout.addRow("Phase steps:", self._n_steps)

        self._period = QDoubleSpinBox()
        self._period.setRange(4.0, 512.0)
        self._period.setValue(16.0)
        self._period.setSuffix(" px")
        capture_layout.addRow("Fringe period:", self._period)

        # -- Phase group --
        phase_group = QGroupBox("Phase Extraction")
        phase_layout = QFormLayout(phase_group)

        self._psa_algorithm = QComboBox()
        self._psa_algorithm.addItems(["N-step"])
        phase_layout.addRow("Algorithm:", self._psa_algorithm)

        # -- Unwrapping group --
        unwrap_group = QGroupBox("Unwrapping")
        unwrap_layout = QFormLayout(unwrap_group)

        self._unwrap_method = QComboBox()
        self._unwrap_method.addItems(["Temporal", "Spatial"])
        unwrap_layout.addRow("Method:", self._unwrap_method)

        # -- Filtering group --
        filter_group = QGroupBox("Filtering")
        filter_layout = QFormLayout(filter_group)

        self._filter_method = QComboBox()
        self._filter_method.addItems(["Gaussian", "Morphological"])
        filter_layout.addRow("Method:", self._filter_method)

        self._filter_cutoff = QDoubleSpinBox()
        self._filter_cutoff.setRange(0.01, 100.0)
        self._filter_cutoff.setValue(0.8)
        self._filter_cutoff.setDecimals(2)
        self._filter_cutoff.setSuffix(" mm")
        filter_layout.addRow("Cutoff λc:", self._filter_cutoff)

        # -- Assemble into scroll area --
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.addWidget(capture_group)
        inner_layout.addWidget(phase_group)
        inner_layout.addWidget(unwrap_group)
        inner_layout.addWidget(filter_group)
        inner_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

        # Connect change signals
        self._n_steps.valueChanged.connect(self._emit_params)
        self._period.valueChanged.connect(self._emit_params)
        self._psa_algorithm.currentIndexChanged.connect(self._emit_params)
        self._unwrap_method.currentIndexChanged.connect(self._emit_params)
        self._filter_method.currentIndexChanged.connect(self._emit_params)
        self._filter_cutoff.valueChanged.connect(self._emit_params)

    def _emit_params(self):
        self.parameters_changed.emit(self.get_params())

    def get_params(self) -> dict:
        period = self._period.value()
        return {
            "n_steps": self._n_steps.value(),
            "period": period,
            "psa_algorithm": self._psa_algorithm.currentText().lower(),
            "unwrap_method": self._unwrap_method.currentText().lower(),
            "filter_method": self._filter_method.currentText().lower(),
            "filter_cutoff": self._filter_cutoff.value(),
            "lambda_eq": period / 50.0,
        }
