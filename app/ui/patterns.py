"""The Patterns pane: pick a pattern (built-in or an image file) and project it.

A dockable picker over `backend.patterns` -- the list holds the built-in
registry plus any images added via "Add Image..."; the knob fields (periods,
pitch) enable per selection, mirroring which parameters the pattern actually
uses. Like the sidebar, it only emits intent (`project_requested`); the main
window generates the pattern and pushes it down the same path as the
measurement fringe.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from backend import patterns

_KEY_ROLE = Qt.UserRole          # the registry key ('fringe_v', ..., 'image')
_PATH_ROLE = Qt.UserRole + 1     # the file path, for 'image' items only


class PatternsPane(QWidget):
    """Dockable pattern picker. Double-click or the Project button projects."""

    project_requested = Signal()  # project the selected pattern

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("patternsPane")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)

        header = QLabel("Pattern Library")
        header.setProperty("role", "sectionHeader")
        layout.addWidget(header)

        self.pattern_list = QListWidget()
        self.pattern_list.setObjectName("patternList")
        for p in patterns.PATTERNS:
            item = QListWidgetItem(p.label)
            item.setData(_KEY_ROLE, p.key)
            item.setToolTip(p.description)
            self.pattern_list.addItem(item)
        self.pattern_list.setCurrentRow(0)
        self.pattern_list.currentItemChanged.connect(self._on_selection_changed)
        self.pattern_list.itemDoubleClicked.connect(
            lambda _item: self.project_requested.emit())
        layout.addWidget(self.pattern_list, 1)

        periods_label = QLabel("Periods")
        periods_label.setObjectName("fieldLabel")
        layout.addWidget(periods_label)
        self.n_periods = QDoubleSpinBox()
        self.n_periods.setObjectName("patternPeriods")
        self.n_periods.setRange(0.5, 256.0)
        self.n_periods.setDecimals(1)
        self.n_periods.setSingleStep(1.0)
        self.n_periods.setValue(8.0)
        self.n_periods.setToolTip("Fringe count across the field (fringe patterns).")
        layout.addWidget(self.n_periods)

        pitch_label = QLabel("Pitch (px)")
        pitch_label.setObjectName("fieldLabel")
        layout.addWidget(pitch_label)
        self.pitch_px = QSpinBox()
        self.pitch_px.setObjectName("patternPitch")
        self.pitch_px.setRange(4, 512)
        self.pitch_px.setSingleStep(4)
        self.pitch_px.setValue(64)
        self.pitch_px.setToolTip("Square/cell size in projector pixels (checkerboard, grid).")
        layout.addWidget(self.pitch_px)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.add_image_button = QPushButton("Add Image...")
        self.add_image_button.setObjectName("addPatternImageButton")
        self.add_image_button.setToolTip(
            "Add an image file to the library; it is shown grayscale, "
            "letterboxed to the projector's aspect."
        )
        self.add_image_button.clicked.connect(self._on_add_image)
        buttons.addWidget(self.add_image_button)
        self.project_button = QPushButton("Project Pattern")
        self.project_button.setObjectName("projectPatternButton")
        self.project_button.setProperty("variant", "primary")
        self.project_button.clicked.connect(lambda: self.project_requested.emit())
        buttons.addWidget(self.project_button)
        layout.addLayout(buttons)

        self._on_selection_changed(self.pattern_list.currentItem(), None)

    # -- selection -------------------------------------------------------------

    def selected_pattern(self) -> tuple[str | None, dict]:
        """The selected pattern's registry key and the kwargs it uses
        (n_periods / pitch_px from the knobs; path for image items)."""
        item = self.pattern_list.currentItem()
        if item is None:
            return None, {}
        key = item.data(_KEY_ROLE)
        if key == patterns.IMAGE_KEY:
            return key, {"path": item.data(_PATH_ROLE)}
        uses = self._uses(key)
        params: dict = {}
        if "n_periods" in uses:
            params["n_periods"] = self.n_periods.value()
        if "pitch_px" in uses:
            params["pitch_px"] = self.pitch_px.value()
        return key, params

    def selected_label(self) -> str:
        item = self.pattern_list.currentItem()
        return item.text() if item is not None else ""

    @staticmethod
    def _uses(key: str) -> tuple[str, ...]:
        for p in patterns.PATTERNS:
            if p.key == key:
                return p.uses
        return ()

    def _on_selection_changed(self, current, _previous) -> None:
        """Only the knobs the selected pattern reads are editable."""
        uses = self._uses(current.data(_KEY_ROLE)) if current is not None else ()
        self.n_periods.setEnabled("n_periods" in uses)
        self.pitch_px.setEnabled("pitch_px" in uses)

    # -- custom images ----------------------------------------------------------

    def _on_add_image(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, "Add Pattern Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)",
        )
        if not path:
            return
        self.add_image(path)

    def add_image(self, path: str) -> None:
        """Append an image file to the library and select it."""
        item = QListWidgetItem(Path(path).name)
        item.setData(_KEY_ROLE, patterns.IMAGE_KEY)
        item.setData(_PATH_ROLE, path)
        item.setToolTip(path)
        self.pattern_list.addItem(item)
        self.pattern_list.setCurrentItem(item)
