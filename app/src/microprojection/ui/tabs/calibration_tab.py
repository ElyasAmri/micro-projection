"""Calibration tab: shows paper-spec priors, runs the (TODO) solver, displays results."""
from __future__ import annotations

import json
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from microprojection.core import paper_specs


class CalibrationTab(QWidget):
    """Calibration workflow UI.

    Layout:
        [ Paper specifications (read-only summary, from paper_specs.py) ]
        [ Calibration workflow buttons: capture target, solve, save ]
        [ Calibrated parameters (filled in after solve completes)     ]
        [ Status / log                                                ]
    """

    calibration_changed = Signal(dict)  # emits the new calibrated parameters

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._calibrated: dict[str, float] = {}
        layout = QVBoxLayout(self)
        layout.addWidget(self._build_paper_specs_group())
        layout.addWidget(self._build_workflow_group())
        layout.addWidget(self._build_calibrated_group())
        layout.addWidget(self._build_log_group(), stretch=1)

    # -- Paper specs (read-only) -------------------------------------------

    def _build_paper_specs_group(self) -> QGroupBox:
        group = QGroupBox("Paper specifications (priors)")
        form = QFormLayout(group)
        s = paper_specs.summary()
        form.addRow("Camera:", QLabel(s["camera_model"]))
        form.addRow("Sensor:", QLabel(
            f'{s["sensor_model"]}  -  '
            f'{s["sensor_px"][0]} x {s["sensor_px"][1]} px '
            f'({s["sensor_mm"][0]:.2f} x {s["sensor_mm"][1]:.2f} mm), '
            f'{s["pixel_pitch_um"]:.2f} um pitch'
        ))
        form.addRow("Telecentric lens:", QLabel(
            f'diameter {s["telecentric_lens_diameter_cm"]:.1f} cm   '
            f'(max field width = lens diameter = '
            f'{s["max_telecentric_field_cm"]:.1f} cm)'
        ))
        form.addRow("Rig geometry:", QLabel(
            f'device spacing {s["device_spacing_cm"]:.1f} cm, '
            f'optical axis height {s["optical_axis_height_cm"]:.1f} cm'
        ))
        form.addRow("Projector:", QLabel(
            f'{s["projector_model"]} / {s["projector_controller"]}'
        ))
        form.addRow("Projector DMD:", QLabel(
            f'{s["projector_dmd_px"][0]} x {s["projector_dmd_px"][1]} px, '
            f'{s["projector_led_nm"]} nm LED'
        ))
        form.addRow("Projector field:", QLabel(
            f'{s["projector_fov_mm"][0]:.0f} x {s["projector_fov_mm"][1]:.0f} mm '
            f'@ {s["projector_working_distance_mm"]:.0f} mm, '
            f'{s["projector_pixel_size_mm"] * 1000:.0f} um/px on plane'
        ))
        return group

    # -- Workflow buttons --------------------------------------------------

    def _build_workflow_group(self) -> QGroupBox:
        group = QGroupBox("Calibration workflow")
        outer = QVBoxLayout(group)
        row = QHBoxLayout()
        self._capture_btn = QPushButton("1. Capture calibration target")
        self._solve_btn = QPushButton("2. Solve calibration")
        self._save_btn = QPushButton("3. Save calibration")
        self._reset_btn = QPushButton("Reset")
        self._capture_btn.clicked.connect(self._on_capture)
        self._solve_btn.clicked.connect(self._on_solve)
        self._save_btn.clicked.connect(self._on_save)
        self._reset_btn.clicked.connect(self._on_reset)
        for b in (self._capture_btn, self._solve_btn, self._save_btn, self._reset_btn):
            row.addWidget(b)
        outer.addLayout(row)
        self._progress = QProgressBar()
        self._progress.setRange(0, 4)
        self._progress.setValue(0)
        outer.addWidget(self._progress)
        return group

    # -- Calibrated parameters display ------------------------------------

    def _build_calibrated_group(self) -> QGroupBox:
        group = QGroupBox("Calibrated parameters")
        self._calib_form = QFormLayout(group)
        labels = [
            ("Pixel pitch on plane (mm/px)", "pixel_pitch_mm"),
            ("Equivalent wavelength lambda_eq (mm)", "lambda_eq_mm"),
            ("Projector-camera baseline (mm)", "baseline_mm"),
            ("Camera incidence angle (deg)", "camera_angle_deg"),
            ("Projector incidence angle (deg)", "projector_angle_deg"),
            ("Field of view on plane (mm x mm)", "field_mm"),
            ("Estimated calibration RMS (px)", "calibration_rms_px"),
        ]
        self._calib_labels: dict[str, QLabel] = {}
        for caption, key in labels:
            lbl = QLabel("--")
            lbl.setStyleSheet("QLabel { font-family: monospace; }")
            self._calib_labels[key] = lbl
            self._calib_form.addRow(caption + ":", lbl)
        return group

    # -- Log ----------------------------------------------------------------

    def _build_log_group(self) -> QGroupBox:
        group = QGroupBox("Status / log")
        layout = QVBoxLayout(group)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("Calibration steps will be logged here.")
        layout.addWidget(self._log)
        return group

    def _log_line(self, text: str) -> None:
        self._log.append(text)

    # -- Workflow actions (placeholders pending hardware integration) ------

    def _on_capture(self) -> None:
        # TODO: trigger the camera + projector to capture a calibration target
        # (checkerboard / dot grid) and store frames. Wire to
        # microprojection.calibration.acquire.acquire_target_frames().
        self._log_line("[capture] would acquire calibration-target frames (TODO: hardware).")
        self._progress.setValue(max(self._progress.value(), 1))

    def _on_solve(self) -> None:
        # TODO: run calibration solver: detect target features, fit camera +
        # projector geometry seeded by paper_specs, return calibrated parameters.
        self._log_line("[solve] would run the calibration solver (TODO: hardware data).")
        # Demo: fill the calibrated fields with paper-specs-derived priors so
        # the UI is exercised end to end.
        from microprojection.calibration.priors import prior_calibration
        params = prior_calibration()
        self.set_calibration(params)
        self._log_line(f"[solve] populated calibrated fields with paper-specs priors: "
                       f"pixel_pitch_mm = {params['pixel_pitch_mm']:.4f}, "
                       f"lambda_eq_mm = {params['lambda_eq_mm']:.4f}")
        self._progress.setValue(max(self._progress.value(), 3))

    def _on_save(self) -> None:
        # TODO: persist calibration to disk; for now log it.
        if not self._calibrated:
            self._log_line("[save] no calibration to save.")
            return
        self._log_line("[save] calibration (JSON):")
        self._log_line(json.dumps(self._calibrated, indent=2))
        self._progress.setValue(4)

    def _on_reset(self) -> None:
        self._calibrated = {}
        for lbl in self._calib_labels.values():
            lbl.setText("--")
        self._progress.setValue(0)
        self._log.clear()

    def set_calibration(self, params: dict[str, float]) -> None:
        """Programmatic entry point used by the solver to populate the panel."""
        self._calibrated = dict(params)
        for key, lbl in self._calib_labels.items():
            value = params.get(key)
            if value is None:
                lbl.setText("--")
            elif isinstance(value, tuple):
                lbl.setText(f"{value[0]:.2f} x {value[1]:.2f}")
            elif isinstance(value, float):
                lbl.setText(f"{value:.4f}")
            else:
                lbl.setText(str(value))
        self.calibration_changed.emit(dict(self._calibrated))
