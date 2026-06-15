"""Left sidebar: device controls for the central layout.

Currently hosts the camera selector (device list + start/stop). Like the panels
under ``ui.panels``, the sidebar only *emits intent*. MainWindow owns the
camera thread and does the orchestration. Add further control groups here as the
design grows.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class Sidebar(QWidget):
    """Fixed-width control rail on the left of the main window."""

    # (backend, index); selecting a device turns it on
    deviceSelected = Signal(str, int)
    previewRequested = Signal()

    WIDTH = 260

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        # resizable via the splitter; keep it usable
        self.setMinimumWidth(240)
        # A plain QWidget ignores QSS background-color unless told to style it.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)

        # "Camera" label inline, before the selector, on the same row.
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Camera"))

        self._camera_combo = QComboBox()
        # Keep the closed box inside the sidebar width but let the popup grow to
        # the full device-name width so long FLIR model/serial strings aren't
        # clipped; the selection is mirrored into a tooltip for the closed box.
        self._camera_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContentsOnFirstShow
        )
        self._camera_combo.setMinimumContentsLength(0)
        self._camera_combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        self._camera_combo.currentIndexChanged.connect(self._on_index_changed)
        # Selecting a camera turns it on (no buttons); list self-refreshes on
        # hot-plug (see DeviceWatcher).
        row.addWidget(self._camera_combo, stretch=1)

        # Preview button on the same row, after the selector. Labeled with a
        # literal dot. Disabled until a camera is selected.
        self._preview_btn = QPushButton(".")
        self._preview_btn.setToolTip("Open camera preview")
        self._preview_btn.setEnabled(False)
        # square button: side = the row/line height (the selector's height)
        side = self._camera_combo.sizeHint().height()
        self._preview_btn.setFixedSize(side, side)
        self._preview_btn.clicked.connect(self.previewRequested)
        row.addWidget(self._preview_btn)

        layout.addLayout(row)
        layout.addStretch(1)

    # Public API used by MainWindow.

    def set_cameras(
        self, cameras: list[dict], prefer_key: tuple[str, int] | None = None
    ) -> None:
        """Repopulate the device list, defaulting to "No camera" (off).

        Always offers a "No camera" entry first. Selection priority:
        1. keep the currently active device if it's still present (so an
           unrelated hot-plug never restarts a running camera);
        2. otherwise, at startup, restore ``prefer_key`` (backend, index) if
           it's present;
        3. otherwise "No camera".
        ``deviceSelected`` is emitted only when the effective selection changes
        (with the ("", -1) sentinel meaning "off").
        """
        prev_key = self._current_key()

        self._camera_combo.blockSignals(True)
        self._camera_combo.clear()
        self._camera_combo.addItem("No camera", None)

        # Default to the "No camera" entry.
        target_idx = 0
        for cam in cameras:
            self._camera_combo.addItem(cam["name"], cam)
            i = self._camera_combo.count() - 1
            self._camera_combo.setItemData(i, cam["name"], Qt.ItemDataRole.ToolTipRole)
            key = (cam["backend"], cam["index"])
            # (1) preserve the active device across rescans
            if key == prev_key:
                target_idx = i
            # (2) restore the remembered selection at startup
            elif prev_key is None and target_idx == 0 and key == prefer_key:
                target_idx = i

        # Size the popup to the widest full name so nothing is clipped.
        widest = max(
            (self._camera_combo.fontMetrics().horizontalAdvance(
                self._camera_combo.itemText(i))
             for i in range(self._camera_combo.count())),
            default=0,
        )
        self._camera_combo.view().setMinimumWidth(widest + 40)
        self._camera_combo.setCurrentIndex(target_idx)
        self._camera_combo.blockSignals(False)

        new_key = self._current_key()
        self._camera_combo.setToolTip(self._camera_combo.currentText())
        self._preview_btn.setEnabled(new_key is not None)
        if new_key != prev_key:
            self._emit_selection(new_key)

    # Internal helpers and slots.

    def _current_key(self):
        cam = self._camera_combo.currentData()
        return (cam["backend"], cam["index"]) if cam else None

    def _emit_selection(self, key) -> None:
        if key is None:
            # off
            self.deviceSelected.emit("", -1)
        else:
            self.deviceSelected.emit(*key)

    def _on_index_changed(self, combo_index: int) -> None:
        cam = self._camera_combo.itemData(combo_index)
        self._camera_combo.setToolTip(cam["name"] if cam else "No camera")
        self._preview_btn.setEnabled(cam is not None)
        self._emit_selection((cam["backend"], cam["index"]) if cam else None)
