"""Camera configuration dialog.

Edits a CameraSettings for the FLIR/PySpin camera: exposure, gain, pixel format,
region of interest, orientation, gamma, frame rate, trigger, and buffer handling.
Opened from the gear button on the sidebar camera row.

There is no Apply button: changing any control applies immediately. The dialog
emits the new CameraSettings; MainWindow applies it to the camera (restarting
acquisition so structural changes such as pixel format and region of interest
take effect) and persists it so it is restored next run.
"""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from microprojection.acquisition.camera_settings import CameraSettings


def _combo(options, current) -> QComboBox:
    """A combo box of (label, data) pairs, preselected to the matching data."""
    box = QComboBox()
    for label, data in options:
        box.addItem(label, data)
    for i in range(box.count()):
        if box.itemData(i) == current:
            box.setCurrentIndex(i)
            break
    return box


class CameraSettingsDialog(QDialog):
    # the edited CameraSettings, emitted on Apply
    settingsChanged = Signal(object)

    _AUTO = [("Off", "Off"), ("Once", "Once"), ("Continuous", "Continuous")]

    def __init__(self, settings: CameraSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Camera settings")
        self.setModal(True)
        self.resize(460, 640)

        self._settings = settings

        outer = QVBoxLayout(self)

        # Many controls, so keep the dialog compact and scroll the body.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        scroll.setWidget(body)
        outer.addWidget(scroll, stretch=1)

        groups = QVBoxLayout(body)
        groups.setSpacing(12)
        groups.addWidget(self._build_exposure_group())
        groups.addWidget(self._build_format_group())
        groups.addWidget(self._build_roi_group())
        groups.addWidget(self._build_acquisition_group())
        groups.addWidget(self._build_trigger_group())
        groups.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._refresh_enabled()
        self._wire_auto_apply()

    def _build_exposure_group(self) -> QGroupBox:
        s = self._settings
        group = QGroupBox("Exposure and gain")
        form = QFormLayout(group)

        self._exposure_auto = _combo(self._AUTO, s.exposure_auto)
        self._exposure_auto.currentIndexChanged.connect(self._refresh_enabled)
        form.addRow("Auto exposure", self._exposure_auto)

        self._exposure_time = QSpinBox()
        self._exposure_time.setRange(1, 30_000_000)
        self._exposure_time.setSuffix(" us")
        self._exposure_time.setValue(int(s.exposure_time_us))
        form.addRow("Exposure time", self._exposure_time)

        self._gain_auto = _combo(self._AUTO, s.gain_auto)
        self._gain_auto.currentIndexChanged.connect(self._refresh_enabled)
        form.addRow("Auto gain", self._gain_auto)

        self._gain = QDoubleSpinBox()
        self._gain.setRange(0.0, 48.0)
        self._gain.setSingleStep(0.1)
        self._gain.setDecimals(1)
        self._gain.setSuffix(" dB")
        self._gain.setValue(s.gain_db)
        form.addRow("Gain", self._gain)
        return group

    def _build_format_group(self) -> QGroupBox:
        s = self._settings
        group = QGroupBox("Image format")
        form = QFormLayout(group)

        self._pixel_format = _combo(
            [
                ("8-bit mono", "Mono8"),
                ("12-bit mono", "Mono12p"),
                ("16-bit mono", "Mono16"),
            ],
            s.pixel_format,
        )
        form.addRow("Pixel format", self._pixel_format)

        self._bit_depth = _combo(
            [
                ("Camera default", None),
                ("8-bit", "Bit8"),
                ("10-bit", "Bit10"),
                ("12-bit", "Bit12"),
                ("14-bit", "Bit14"),
            ],
            s.bit_depth,
        )
        form.addRow("Bit depth", self._bit_depth)

        self._binning_h = QSpinBox()
        self._binning_h.setRange(1, 16)
        self._binning_h.setValue(s.binning_horizontal)
        form.addRow("Binning horizontal", self._binning_h)

        self._binning_v = QSpinBox()
        self._binning_v.setRange(1, 16)
        self._binning_v.setValue(s.binning_vertical)
        form.addRow("Binning vertical", self._binning_v)

        self._reverse_x = QCheckBox()
        self._reverse_x.setChecked(s.reverse_x)
        form.addRow("Reverse x", self._reverse_x)

        self._reverse_y = QCheckBox()
        self._reverse_y.setChecked(s.reverse_y)
        form.addRow("Reverse y", self._reverse_y)
        return group

    def _build_roi_group(self) -> QGroupBox:
        s = self._settings
        group = QGroupBox("Region of interest")
        form = QFormLayout(group)

        self._roi_enable = QCheckBox("Crop to a region")
        self._roi_enable.setChecked(s.roi_enable)
        self._roi_enable.toggled.connect(self._refresh_enabled)
        form.addRow("Enable", self._roi_enable)

        self._roi_width = QSpinBox()
        self._roi_width.setRange(0, 100_000)
        self._roi_width.setValue(s.roi_width)
        form.addRow("Width", self._roi_width)

        self._roi_height = QSpinBox()
        self._roi_height.setRange(0, 100_000)
        self._roi_height.setValue(s.roi_height)
        form.addRow("Height", self._roi_height)

        self._roi_offset_x = QSpinBox()
        self._roi_offset_x.setRange(0, 100_000)
        self._roi_offset_x.setValue(s.roi_offset_x)
        form.addRow("Offset x", self._roi_offset_x)

        self._roi_offset_y = QSpinBox()
        self._roi_offset_y.setRange(0, 100_000)
        self._roi_offset_y.setValue(s.roi_offset_y)
        form.addRow("Offset y", self._roi_offset_y)
        return group

    def _build_acquisition_group(self) -> QGroupBox:
        s = self._settings
        group = QGroupBox("Acquisition")
        form = QFormLayout(group)

        self._frame_rate_enable = QCheckBox("Set frame rate manually")
        self._frame_rate_enable.setChecked(s.frame_rate_enable)
        self._frame_rate_enable.toggled.connect(self._refresh_enabled)
        form.addRow("Frame rate", self._frame_rate_enable)

        self._frame_rate = QDoubleSpinBox()
        self._frame_rate.setRange(1.0, 1000.0)
        self._frame_rate.setDecimals(2)
        self._frame_rate.setSuffix(" fps")
        self._frame_rate.setValue(s.frame_rate)
        form.addRow("Rate", self._frame_rate)

        self._gamma_enable = QCheckBox("Apply gamma curve")
        self._gamma_enable.setChecked(s.gamma_enable)
        self._gamma_enable.toggled.connect(self._refresh_enabled)
        form.addRow("Gamma", self._gamma_enable)

        self._gamma = QDoubleSpinBox()
        self._gamma.setRange(0.1, 4.0)
        self._gamma.setSingleStep(0.05)
        self._gamma.setDecimals(2)
        self._gamma.setValue(s.gamma)
        form.addRow("Gamma value", self._gamma)

        self._buffer_mode = _combo(
            [("Newest only", "NewestOnly"), ("Oldest first", "OldestFirst")],
            s.stream_buffer_mode,
        )
        form.addRow("Buffer handling", self._buffer_mode)
        return group

    def _build_trigger_group(self) -> QGroupBox:
        s = self._settings
        group = QGroupBox("Trigger")
        form = QFormLayout(group)

        self._trigger_mode = _combo(
            [("Off", "Off"), ("Software", "Software"), ("Hardware", "Hardware")],
            s.trigger_mode,
        )
        self._trigger_mode.currentIndexChanged.connect(self._refresh_enabled)
        form.addRow("Mode", self._trigger_mode)

        self._trigger_source = _combo(
            [
                ("Line 0", "Line0"),
                ("Line 1", "Line1"),
                ("Line 2", "Line2"),
                ("Line 3", "Line3"),
            ],
            s.trigger_source,
        )
        form.addRow("Source", self._trigger_source)

        self._trigger_activation = _combo(
            [("Rising", "RisingEdge"), ("Falling", "FallingEdge")],
            s.trigger_activation,
        )
        form.addRow("Edge", self._trigger_activation)
        return group

    def _wire_auto_apply(self):
        """Apply on every change so the camera updates without an Apply button.

        Spin boxes use editingFinished (commit on Enter or focus-out) so typing
        a value does not restart the camera on every digit; combos and check
        boxes apply on their change signal.
        """
        for combo in (
            self._exposure_auto,
            self._gain_auto,
            self._pixel_format,
            self._bit_depth,
            self._buffer_mode,
            self._trigger_mode,
            self._trigger_source,
            self._trigger_activation,
        ):
            combo.currentIndexChanged.connect(self._apply)
        for spin in (
            self._exposure_time,
            self._gain,
            self._binning_h,
            self._binning_v,
            self._roi_width,
            self._roi_height,
            self._roi_offset_x,
            self._roi_offset_y,
            self._frame_rate,
            self._gamma,
        ):
            spin.editingFinished.connect(self._apply)
        for check in (
            self._reverse_x,
            self._reverse_y,
            self._roi_enable,
            self._frame_rate_enable,
            self._gamma_enable,
        ):
            check.toggled.connect(self._apply)

    def _refresh_enabled(self, *_):
        # Fixed exposure/gain fields only matter when their auto mode is off.
        self._exposure_time.setEnabled(self._exposure_auto.currentData() == "Off")
        self._gain.setEnabled(self._gain_auto.currentData() == "Off")
        roi = self._roi_enable.isChecked()
        for widget in (
            self._roi_width,
            self._roi_height,
            self._roi_offset_x,
            self._roi_offset_y,
        ):
            widget.setEnabled(roi)
        self._frame_rate.setEnabled(self._frame_rate_enable.isChecked())
        self._gamma.setEnabled(self._gamma_enable.isChecked())
        # Source and edge apply to an external hardware line only.
        hardware = self._trigger_mode.currentData() == "Hardware"
        self._trigger_source.setEnabled(hardware)
        self._trigger_activation.setEnabled(hardware)

    def _collect(self) -> CameraSettings:
        return replace(
            self._settings,
            exposure_auto=self._exposure_auto.currentData(),
            exposure_time_us=float(self._exposure_time.value()),
            gain_auto=self._gain_auto.currentData(),
            gain_db=self._gain.value(),
            pixel_format=self._pixel_format.currentData(),
            bit_depth=self._bit_depth.currentData(),
            roi_enable=self._roi_enable.isChecked(),
            roi_width=self._roi_width.value(),
            roi_height=self._roi_height.value(),
            roi_offset_x=self._roi_offset_x.value(),
            roi_offset_y=self._roi_offset_y.value(),
            binning_horizontal=self._binning_h.value(),
            binning_vertical=self._binning_v.value(),
            reverse_x=self._reverse_x.isChecked(),
            reverse_y=self._reverse_y.isChecked(),
            gamma_enable=self._gamma_enable.isChecked(),
            gamma=self._gamma.value(),
            frame_rate_enable=self._frame_rate_enable.isChecked(),
            frame_rate=self._frame_rate.value(),
            trigger_mode=self._trigger_mode.currentData(),
            trigger_source=self._trigger_source.currentData(),
            trigger_activation=self._trigger_activation.currentData(),
            stream_buffer_mode=self._buffer_mode.currentData(),
        )

    def _apply(self):
        self._settings = self._collect()
        self.settingsChanged.emit(self._settings)
