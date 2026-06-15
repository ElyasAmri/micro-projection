from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QVBoxLayout, QWidget

from microprojection.core.datatypes import PipelineResult

_PARAMS = ["Sa", "Sq", "Sz", "Ssk", "Sku"]


class ResultsPanel(QWidget):
    """Displays computed roughness parameters."""

    def __init__(self, parent=None):
        super().__init__(parent)

        group = QGroupBox("Roughness Parameters")
        form = QFormLayout(group)

        self._labels: dict[str, QLabel] = {}
        for name in _PARAMS:
            label = QLabel("--")
            label.setStyleSheet("QLabel { font-family: monospace; }")
            self._labels[name] = label
            form.addRow(f"{name}:", label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(group)
        layout.addStretch()

    def update_roughness(self, result: PipelineResult):
        for name in _PARAMS:
            value = result.roughness.get(name)
            if value is not None:
                self._labels[name].setText(f"{value:.6f}")
            else:
                self._labels[name].setText("--")
