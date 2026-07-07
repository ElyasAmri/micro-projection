"""The Camera Settings panel: edit the `CameraSettings` the next capture uses.

A modeless dialog (so it can stay open through the tweak-capture-look loop)
over the shared settings record in `hardware.camera_config`. Apply pushes the
form into that record and persists it via QSettings, so the rig comes back up
with the same camera state; Restore Defaults refills the form (including the
MP_CAM_EXPOSURE_US seed) without applying.

The settings take effect at the start of the next capture -- the camera is
opened, configured, and closed per capture run -- so nothing here talks to the
device directly, and the panel works identically with or without a camera
attached.
"""
from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from hardware.camera_config import (
    CameraSettings,
    default_camera_settings,
    set_camera_settings,
)
from logbus import get_logger, success

log = get_logger("camera")

_PREFIX = "camera/"  # QSettings key prefix, one key per CameraSettings field


def saved_camera_settings() -> CameraSettings:
    """The persisted settings, over the defaults for anything never saved."""
    d = default_camera_settings()
    q = QSettings()
    return CameraSettings(
        exposure_auto=q.value(_PREFIX + "exposure_auto", d.exposure_auto, type=bool),
        exposure_us=q.value(_PREFIX + "exposure_us", d.exposure_us, type=float),
        gain_auto=q.value(_PREFIX + "gain_auto", d.gain_auto, type=bool),
        gain_db=q.value(_PREFIX + "gain_db", d.gain_db, type=float),
        gamma_enabled=q.value(_PREFIX + "gamma_enabled", d.gamma_enabled, type=bool),
        gamma=q.value(_PREFIX + "gamma", d.gamma, type=float),
        black_level_pct=q.value(_PREFIX + "black_level_pct", d.black_level_pct, type=float),
    )


def persist_camera_settings(s: CameraSettings) -> None:
    """Write the settings so the next session starts from them."""
    q = QSettings()
    q.setValue(_PREFIX + "exposure_auto", s.exposure_auto)
    q.setValue(_PREFIX + "exposure_us", s.exposure_us)
    q.setValue(_PREFIX + "gain_auto", s.gain_auto)
    q.setValue(_PREFIX + "gain_db", s.gain_db)
    q.setValue(_PREFIX + "gamma_enabled", s.gamma_enabled)
    q.setValue(_PREFIX + "gamma", s.gamma)
    q.setValue(_PREFIX + "black_level_pct", s.black_level_pct)


def apply_camera_settings(s: CameraSettings) -> None:
    """Make `s` live (next capture) and persist it (next session)."""
    set_camera_settings(s)
    persist_camera_settings(s)


class CameraSettingsDialog(QDialog):
    """Form over `CameraSettings`. Apply keeps the dialog open; values land on
    the device when the next capture opens the camera."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("cameraSettingsDialog")
        self.setWindowTitle("Camera Settings")
        self.setModal(False)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        layout.addLayout(grid)
        row = 0

        def header(text: str) -> None:
            nonlocal row
            label = QLabel(text)
            label.setProperty("role", "sectionHeader")
            grid.addWidget(label, row, 0, 1, 2)
            row += 1

        def field(label_text: str, widget) -> None:
            nonlocal row
            label = QLabel(label_text)
            label.setObjectName("fieldLabel")
            grid.addWidget(label, row, 0, Qt.AlignVCenter)
            grid.addWidget(widget, row, 1)
            row += 1

        # -- Exposure: the setting that makes or breaks a phase-shift scan ---
        header("Exposure")
        self.exposure_auto = QCheckBox("Auto (continuous re-metering)")
        self.exposure_auto.setToolTip(
            "Leave OFF for scans: auto-exposure re-meters between phase steps, "
            "which swings the per-frame brightness and ripples the height map."
        )
        grid.addWidget(self.exposure_auto, row, 0, 1, 2)
        row += 1

        self.exposure_us = QDoubleSpinBox()
        self.exposure_us.setObjectName("exposureUs")
        self.exposure_us.setRange(20.0, 5_000_000.0)
        self.exposure_us.setDecimals(0)
        self.exposure_us.setSingleStep(500.0)
        self.exposure_us.setSuffix(" µs")
        self.exposure_us.setToolTip(
            "Fixed exposure time. Clamped to the camera's own range at apply."
        )
        field("Exposure time", self.exposure_us)
        self.exposure_auto.toggled.connect(self.exposure_us.setDisabled)

        # -- Gain -------------------------------------------------------------
        header("Gain")
        self.gain_auto = QCheckBox("Auto (continuous)")
        self.gain_auto.setToolTip(
            "Fix the gain for scans, same reasoning as exposure: every frame "
            "of the stack should be imaged identically."
        )
        grid.addWidget(self.gain_auto, row, 0, 1, 2)
        row += 1

        self.gain_db = QDoubleSpinBox()
        self.gain_db.setObjectName("gainDb")
        self.gain_db.setRange(0.0, 48.0)
        self.gain_db.setDecimals(1)
        self.gain_db.setSingleStep(0.5)
        self.gain_db.setSuffix(" dB")
        field("Gain", self.gain_db)
        self.gain_auto.toggled.connect(self.gain_db.setDisabled)

        # -- Gamma ------------------------------------------------------------
        header("Gamma")
        self.gamma_enabled = QCheckBox("Enable gamma")
        self.gamma_enabled.setToolTip(
            "Keep OFF for measurement: the reconstruction assumes the fringe "
            "sinusoid is imaged linearly, and gamma bends exactly that."
        )
        grid.addWidget(self.gamma_enabled, row, 0, 1, 2)
        row += 1

        self.gamma = QDoubleSpinBox()
        self.gamma.setObjectName("gammaValue")
        self.gamma.setRange(0.25, 4.0)
        self.gamma.setDecimals(2)
        self.gamma.setSingleStep(0.05)
        field("Gamma", self.gamma)
        self.gamma_enabled.toggled.connect(self.gamma.setEnabled)

        # -- Black level -------------------------------------------------------
        header("Black Level")
        self.black_level = QDoubleSpinBox()
        self.black_level.setObjectName("blackLevel")
        self.black_level.setRange(0.0, 15.0)
        self.black_level.setDecimals(2)
        self.black_level.setSingleStep(0.25)
        self.black_level.setSuffix(" %")
        self.black_level.setToolTip("Sensor black level offset (all channels).")
        field("Offset", self.black_level)

        note = QLabel("Applied to the FLIR camera at the start of the next capture.")
        note.setObjectName("fieldLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QHBoxLayout()
        defaults_button = QPushButton("Restore Defaults")
        defaults_button.setToolTip(
            "Refill the form with the defaults (honors MP_CAM_EXPOSURE_US); "
            "nothing changes until Apply."
        )
        defaults_button.clicked.connect(lambda: self.load_settings(default_camera_settings()))
        buttons.addWidget(defaults_button)
        buttons.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        buttons.addWidget(close_button)
        apply_button = QPushButton("Apply")
        apply_button.setProperty("variant", "primary")
        apply_button.clicked.connect(self._on_apply)
        buttons.addWidget(apply_button)
        layout.addLayout(buttons)

        self.load_settings(saved_camera_settings())

    # -- form <-> settings -----------------------------------------------------

    def load_settings(self, s: CameraSettings) -> None:
        """Fill the form from a settings record (does not apply)."""
        self.exposure_auto.setChecked(s.exposure_auto)
        self.exposure_us.setValue(s.exposure_us)
        self.exposure_us.setDisabled(s.exposure_auto)
        self.gain_auto.setChecked(s.gain_auto)
        self.gain_db.setValue(s.gain_db)
        self.gain_db.setDisabled(s.gain_auto)
        self.gamma_enabled.setChecked(s.gamma_enabled)
        self.gamma.setValue(s.gamma)
        self.gamma.setEnabled(s.gamma_enabled)
        self.black_level.setValue(s.black_level_pct)

    def current_settings(self) -> CameraSettings:
        """The settings record the form currently describes."""
        return CameraSettings(
            exposure_auto=self.exposure_auto.isChecked(),
            exposure_us=self.exposure_us.value(),
            gain_auto=self.gain_auto.isChecked(),
            gain_db=self.gain_db.value(),
            gamma_enabled=self.gamma_enabled.isChecked(),
            gamma=self.gamma.value(),
            black_level_pct=self.black_level.value(),
        )

    def _on_apply(self) -> None:
        s = self.current_settings()
        apply_camera_settings(s)
        exposure = "auto" if s.exposure_auto else f"{s.exposure_us:.0f} µs"
        gain = "auto" if s.gain_auto else f"{s.gain_db:.1f} dB"
        success(log, f"camera settings applied (next capture): exposure {exposure}, "
                     f"gain {gain}, gamma {'on' if s.gamma_enabled else 'off'}")
