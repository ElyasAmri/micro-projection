"""Camera configuration dialog.

A modal shell for camera controls (exposure, gain, pixel format, region of
interest, etc.). Empty for now; controls land here as they are added. Opened
from the gear button on the sidebar camera row.
"""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout


class CameraSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Camera settings")
        self.setModal(True)
        self.resize(420, 300)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("No camera settings yet."))
        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
