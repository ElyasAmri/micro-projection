"""Projector configuration dialog.

Chooses a temporary projection for setup and focus calibration: nothing (blank),
a real-time generated test pattern (fringe, Siemens star, or cross-hair), or a
specific image file. Opened from the gear button on the sidebar projector row.

There is no apply button: changing the selection projects immediately. The
dialog only emits intent. MainWindow generates the pattern at the projector
resolution and drives the projector window.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ProjectorSettingsDialog(QDialog):
    # spec dict describing the wanted projection
    projectionRequested = Signal(dict)
    # blank the projector (project black)
    projectionCleared = Signal()

    _OPTIONS = [
        ("None", "none"),
        ("Fringe", "fringe"),
        ("Siemens star", "star"),
        ("Cross-hair", "crosshair"),
        ("Image file", "image"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Projector settings")
        self.setModal(True)
        self.resize(440, 200)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Projection chooser: switching it projects immediately.
        chooser = QHBoxLayout()
        chooser.addWidget(QLabel("Projection"))
        self._combo = QComboBox()
        for label, key in self._OPTIONS:
            self._combo.addItem(label, key)
        chooser.addWidget(self._combo, stretch=1)
        layout.addLayout(chooser)

        layout.addWidget(self._build_period_row())
        layout.addWidget(self._build_image_row())
        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Reflect the initial selection without projecting; only user changes
        # from here trigger a projection.
        self._sync_visibility()
        self._combo.currentIndexChanged.connect(self._on_change)
        self._period_spin.valueChanged.connect(self._apply)

    def _build_period_row(self) -> QWidget:
        self._period_row = QWidget()
        row = QHBoxLayout(self._period_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("Period"))
        self._period_spin = QSpinBox()
        self._period_spin.setRange(2, 4000)
        self._period_spin.setValue(32)
        self._period_spin.setSuffix(" px")
        row.addWidget(self._period_spin)
        row.addStretch(1)
        return self._period_row

    def _build_image_row(self) -> QWidget:
        self._image_row = QWidget()
        row = QHBoxLayout(self._image_row)
        row.setContentsMargins(0, 0, 0, 0)
        self._image_path = QLineEdit()
        self._image_path.setReadOnly(True)
        self._image_path.setPlaceholderText("No file selected")
        row.addWidget(self._image_path, stretch=1)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        return self._image_row

    def _sync_visibility(self):
        key = self._combo.currentData()
        self._period_row.setVisible(key == "fringe")
        self._image_row.setVisible(key == "image")

    def _on_change(self, *_):
        self._sync_visibility()
        self._apply()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)",
        )
        if path:
            self._image_path.setText(path)
            self._apply()

    def _apply(self, *_):
        key = self._combo.currentData()
        if key == "none":
            self.projectionCleared.emit()
            return
        if key == "image":
            path = self._image_path.text()
            # wait for a file before projecting
            if path:
                self.projectionRequested.emit({"source": "image", "path": path})
            return
        self.projectionRequested.emit({
            "source": "pattern",
            "pattern": key,
            "period": self._period_spin.value(),
            "orientation": "vertical",
        })
