"""Projector control panel: DLPC350 USB control + HDMI synced-capture trigger.

First-class UI for the PRO4500 integration. Exposes device detection, power and
display-mode control over USB (DLPC350 / pycrafter4500), pattern-sequence
parameters, and the HDMI synced-capture action. The panel only *emits intent* —
MainWindow owns the controller, camera, and pipeline and does the orchestration.

USB controls disable themselves when pycrafter4500 is unavailable; the HDMI
synced-capture path stays usable regardless (it drives the on-screen projector
window, not the USB link).
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from microprojection.core import paper_specs


class ProjectorPanel(QWidget):
    """Controls for the PRO4500 projector (USB control + HDMI capture)."""

    detectRequested = Signal()
    powerUpRequested = Signal()
    powerDownRequested = Signal()
    videoModeRequested = Signal()
    patternModeRequested = Signal(dict)   # {fps, bit_depth, led_color}
    stopSequenceRequested = Signal()
    captureRequested = Signal(dict)       # {settle_ms}

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller

        # -- Device ---------------------------------------------------------
        device_group = QGroupBox("Projector device (DLPC350 / USB)")
        device_layout = QVBoxLayout(device_group)
        row = QHBoxLayout()
        self._device_combo = QComboBox()
        self._device_combo.addItem("No projector detected")
        self._refresh_btn = QPushButton("Detect")
        self._refresh_btn.clicked.connect(self._on_detect)
        row.addWidget(self._device_combo, stretch=1)
        row.addWidget(self._refresh_btn)
        device_layout.addLayout(row)

        # -- Power / mode ---------------------------------------------------
        power_group = QGroupBox("Power / display mode")
        power_layout = QHBoxLayout(power_group)
        self._power_up_btn = QPushButton("Power Up")
        self._power_down_btn = QPushButton("Power Down")
        self._video_btn = QPushButton("Video Mode")
        self._power_up_btn.clicked.connect(lambda: self.powerUpRequested.emit())
        self._power_down_btn.clicked.connect(lambda: self.powerDownRequested.emit())
        self._video_btn.clicked.connect(lambda: self.videoModeRequested.emit())
        for b in (self._power_up_btn, self._power_down_btn, self._video_btn):
            power_layout.addWidget(b)

        # -- Pattern sequence ----------------------------------------------
        pattern_group = QGroupBox("Pattern sequence (USB, high-speed)")
        pattern_layout = QFormLayout(pattern_group)
        self._fps = QSpinBox()
        self._fps.setRange(1, 4255)
        self._fps.setValue(int(paper_specs.PROJECTOR_HDMI_GRAYSCALE_FPS))
        self._fps.setSuffix(" Hz")
        pattern_layout.addRow("Sequence rate:", self._fps)

        self._bit_depth = QSpinBox()
        self._bit_depth.setRange(1, 8)
        self._bit_depth.setValue(8)
        self._bit_depth.setSuffix(" bit")
        pattern_layout.addRow("Bit depth:", self._bit_depth)

        led_row = QHBoxLayout()
        self._led_r = QCheckBox("R")
        self._led_g = QCheckBox("G")
        self._led_b = QCheckBox("B")
        for c in (self._led_r, self._led_g, self._led_b):
            c.setChecked(True)
            led_row.addWidget(c)
        led_widget = QWidget()
        led_widget.setLayout(led_row)
        pattern_layout.addRow("LEDs:", led_widget)

        seq_btns = QHBoxLayout()
        self._pattern_btn = QPushButton("Start Pattern Mode")
        self._stop_btn = QPushButton("Stop Sequence")
        self._pattern_btn.clicked.connect(self._on_pattern_mode)
        self._stop_btn.clicked.connect(lambda: self.stopSequenceRequested.emit())
        seq_btns.addWidget(self._pattern_btn)
        seq_btns.addWidget(self._stop_btn)
        pattern_layout.addRow(seq_btns)

        # -- HDMI synced capture -------------------------------------------
        capture_group = QGroupBox("HDMI synced capture")
        capture_layout = QFormLayout(capture_group)
        self._settle = QSpinBox()
        self._settle.setRange(20, 5000)
        self._settle.setValue(200)
        self._settle.setSuffix(" ms")
        capture_layout.addRow("Settle per step:", self._settle)
        self._capture_btn = QPushButton("Run Projector Capture")
        self._capture_btn.clicked.connect(self._on_capture)
        capture_layout.addRow(self._capture_btn)

        # -- Status ---------------------------------------------------------
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("QLabel { color: #aaa; }")

        # -- Assemble -------------------------------------------------------
        layout = QVBoxLayout(self)
        layout.addWidget(device_group)
        layout.addWidget(power_group)
        layout.addWidget(pattern_group)
        layout.addWidget(capture_group)
        layout.addWidget(self._status)
        layout.addStretch()

        self._usb_widgets = [
            self._power_up_btn, self._power_down_btn, self._video_btn,
            self._fps, self._bit_depth, self._led_r, self._led_g, self._led_b,
            self._pattern_btn, self._stop_btn,
        ]
        if not getattr(controller, "available", False):
            for w in self._usb_widgets:
                w.setEnabled(False)
            self.set_status(
                "pycrafter4500 not installed — USB control disabled. "
                "HDMI synced capture still works. Install: pip install -e .[hardware]"
            )

    # -- public API used by MainWindow -------------------------------------

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def set_devices(self, devices: list[dict]) -> None:
        self._device_combo.clear()
        if not devices:
            self._device_combo.addItem("No projector detected")
            return
        for d in devices:
            self._device_combo.addItem(d.get("name", str(d)))

    def set_busy(self, busy: bool) -> None:
        """Disable action buttons while a capture is running."""
        self._capture_btn.setEnabled(not busy)
        if getattr(self._controller, "available", False):
            self._pattern_btn.setEnabled(not busy)

    def led_color(self) -> int:
        return (
            (1 if self._led_r.isChecked() else 0)
            | (2 if self._led_g.isChecked() else 0)
            | (4 if self._led_b.isChecked() else 0)
        )

    # -- internal slots ----------------------------------------------------

    def _on_detect(self) -> None:
        self.detectRequested.emit()

    def _on_pattern_mode(self) -> None:
        self.patternModeRequested.emit(
            {
                "fps": float(self._fps.value()),
                "bit_depth": int(self._bit_depth.value()),
                "led_color": self.led_color(),
            }
        )

    def _on_capture(self) -> None:
        self.captureRequested.emit({"settle_ms": int(self._settle.value())})
