from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QComboBox, QFrame, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from ..core.constants import DEFAULT_DEVICE_SPACING_CM
from .reconstruction_view import ReconstructionWindow


class ProjectionControlsMixin:
    def _init_controls(self) -> None:
        self._controls_frame = QFrame(self)
        self._controls_frame.setStyleSheet(
            "QFrame { background-color: rgba(20, 20, 20, 170); border: 1px solid #505050; border-radius: 6px; }"
            "QLabel { color: #E6E6E6; }"
            "QPushButton { color: #E6E6E6; background-color: rgba(55, 55, 55, 210); border: 1px solid #6a6a6a; border-radius: 4px; padding: 6px; }"
            "QPushButton:disabled { color: #A0A0A0; background-color: rgba(45, 45, 45, 180); border-color: #555555; }"
        )
        layout = QVBoxLayout(self._controls_frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        self._spacing_label = QLabel(self._controls_frame)
        self._spacing_slider = QSlider(Qt.Horizontal, self._controls_frame)
        spacing_max = max(1, int(round(max(5.0, self._device_distance_m * 2.0) * 10.0)))
        self._spacing_slider.setRange(0, spacing_max)
        spacing_value = int(round(max(0.0, getattr(self, "_device_spacing_cm", 0.0)) * 10.0))
        self._spacing_slider.setValue(min(spacing_value, spacing_max))
        self._spacing_slider.valueChanged.connect(self._on_spacing_changed)

        self._distance_label = QLabel(self._controls_frame)
        self._distance_slider = QSlider(Qt.Horizontal, self._controls_frame)
        self._distance_slider.setRange(10, 5000)
        self._distance_slider.setValue(int(round(self.distance_m * 10.0)))
        self._distance_slider.valueChanged.connect(self._on_distance_changed)

        self._projector_fov_label = QLabel(self._controls_frame)
        self._projector_fov_slider = QSlider(Qt.Horizontal, self._controls_frame)
        self._projector_fov_slider.setRange(0, 140)
        initial_fov = (
            self.projector_fov_deg
            if self.projector_fov_deg is not None
            else self._effective_projector_fov_now()
        )
        self._projector_fov_slider.setValue(int(round(initial_fov)))
        self._projector_fov_slider.valueChanged.connect(self._on_projector_fov_changed)

        self._reset_controls_button = QPushButton("Reset controls to default", self._controls_frame)
        self._reset_controls_button.clicked.connect(self._on_reset_controls_clicked)

        self._object_label = QLabel("3D object", self._controls_frame)
        self._object_combo = QComboBox(self._controls_frame)
        self._object_combo.addItem("Default box", "box")
        self._object_combo.addItem("Nuanced height field", "nuanced")
        self._object_combo.currentIndexChanged.connect(self._on_object_kind_changed)

        self._record_sweep_button = QPushButton("Record surface camera sweep", self._controls_frame)
        self._record_sweep_button.setEnabled(self.projection_source == "fringe")
        self._record_sweep_button.clicked.connect(self._on_record_sweep_clicked)

        self._scan_reconstruct_button = QPushButton("Scan and reconstruct", self._controls_frame)
        self._scan_reconstruct_button.setEnabled(self.projection_source == "fringe")
        self._scan_reconstruct_button.clicked.connect(self._on_scan_reconstruct_clicked)

        layout.addWidget(self._spacing_label)
        layout.addWidget(self._spacing_slider)
        layout.addWidget(self._distance_label)
        layout.addWidget(self._distance_slider)
        layout.addWidget(self._projector_fov_label)
        layout.addWidget(self._projector_fov_slider)
        layout.addWidget(self._reset_controls_button)
        layout.addWidget(self._object_label)
        layout.addWidget(self._object_combo)
        layout.addWidget(self._record_sweep_button)
        layout.addWidget(self._scan_reconstruct_button)
        self._refresh_control_labels()
        self._controls_frame.setVisible(self.mode == "plane3d")

    def _refresh_control_labels(self) -> None:
        if hasattr(self, "_spacing_label"):
            self._spacing_label.setText(
                f"Proj-telecentric spacing (ray origins): {self._device_spacing_cm:.1f} cm"
            )
        if hasattr(self, "_spacing_slider"):
            spacing_max = max(1, int(round(max(5.0, self._device_distance_m * 2.0) * 10.0)))
            if self._spacing_slider.maximum() != spacing_max:
                self._spacing_slider.setRange(0, spacing_max)
            spacing_value = int(round(max(0.0, self._device_spacing_cm) * 10.0))
            spacing_value = min(spacing_value, spacing_max)
            if self._spacing_slider.value() != spacing_value:
                self._spacing_slider.blockSignals(True)
                self._spacing_slider.setValue(spacing_value)
                self._spacing_slider.blockSignals(False)
        self._distance_label.setText(f"Plane distance: {self.distance_m:.1f} cm")
        if self.projector_fov_deg is None:
            effective = self._effective_projector_fov_now()
            self._projector_fov_label.setText(f"Projector FOV: Auto ({effective:.1f}°)")
            self._projector_fov_slider.blockSignals(True)
            self._projector_fov_slider.setValue(int(round(effective)))
            self._projector_fov_slider.blockSignals(False)
        else:
            self._projector_fov_label.setText(f"Projector FOV: {self.projector_fov_deg:.1f}°")
            self._projector_fov_slider.blockSignals(True)
            self._projector_fov_slider.setValue(int(round(self.projector_fov_deg)))
            self._projector_fov_slider.blockSignals(False)
        if hasattr(self, "_record_sweep_button"):
            self._record_sweep_button.setEnabled(
                self.mode == "plane3d"
                and self.projection_source == "fringe"
                and not self._recording_video
            )
        if hasattr(self, "_scan_reconstruct_button"):
            self._scan_reconstruct_button.setEnabled(
                self.mode == "plane3d"
                and self.projection_source == "fringe"
                and not self._scan_in_progress
            )
        if hasattr(self, "_object_combo"):
            index = self._object_combo.findData(self.field_object_kind)
            if index >= 0 and index != self._object_combo.currentIndex():
                self._object_combo.blockSignals(True)
                self._object_combo.setCurrentIndex(index)
                self._object_combo.blockSignals(False)

    def _on_spacing_changed(self, value: int) -> None:
        self._device_spacing_cm = max(0.0, float(value) / 10.0)
        self._update_reflected_devices()
        self._refresh_control_labels()
        self.update()

    def _on_distance_changed(self, value: int) -> None:
        self.distance_m = max(0.2, float(value) / 10.0)
        self._update_reflected_devices()
        self._refresh_control_labels()
        self.update()

    def _on_projector_fov_changed(self, value: int) -> None:
        if value <= 0:
            self.projector_fov_deg = None
        else:
            self.projector_fov_deg = float(value)
        self._refresh_control_labels()
        self.update()

    def _on_object_kind_changed(self, index: int) -> None:
        kind = self._object_combo.itemData(index)
        self.field_object_kind = str(kind or "box")
        self.project_field_object = True
        self.update()

    def _on_reset_controls_clicked(self) -> None:
        self._device_spacing_cm = self._default_device_spacing_cm
        self.distance_m = self._default_distance_m
        self.projector_fov_deg = self._default_projector_fov_setting
        self._update_reflected_devices()
        self._refresh_control_labels()
        self.update()

    def _on_record_sweep_clicked(self) -> None:
        if self._recording_video:
            return
        if self.projection_source != "fringe":
            QMessageBox.warning(
                self,
                "Recording unavailable",
                "Surface-camera sweep recording requires fringe projection source.",
            )
            return

        default_output_path = Path(".artifacts") / "surface-camera-sweep.mp4"
        default_output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save surface camera sweep video",
            str(default_output_path),
            "MP4 Video (*.mp4);;All Files (*)",
        )
        if not output_path:
            return
        if Path(output_path).suffix == "":
            output_path = f"{output_path}.mp4"

        self._recording_video = True
        self._record_sweep_button.setEnabled(False)
        self._record_sweep_button.setText("Recording...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.record_viewport_sweep_video(output_path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Recording failed", str(exc))
        else:
            QMessageBox.information(
                self,
                "Recording complete",
                f"Saved surface camera sweep video to:\n{output_path}",
            )
        finally:
            QApplication.restoreOverrideCursor()
            self._recording_video = False
            self._record_sweep_button.setText("Record surface camera sweep")
            self._record_sweep_button.setEnabled(
                self.mode == "plane3d" and self.projection_source == "fringe"
            )

    def _on_scan_reconstruct_clicked(self) -> None:
        if self._scan_in_progress:
            return
        if self.projection_source != "fringe":
            QMessageBox.warning(
                self,
                "Scan unavailable",
                "Surface reconstruction requires fringe projection source.",
            )
            return

        self._scan_in_progress = True
        self._scan_reconstruct_button.setText("Scanning...")
        self._refresh_control_labels()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        record_path = Path(".artifacts") / "viewport-scan-sweep.mp4"
        try:
            reconstruction = self.reconstruct_current_object_from_viewport(
                record_path=record_path,
            )
        except (RuntimeError, ValueError) as exc:
            QMessageBox.critical(self, "Scan failed", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
            self._scan_in_progress = False
            self._scan_reconstruct_button.setText("Scan and reconstruct")
            self._refresh_control_labels()

        window = ReconstructionWindow(reconstruction)
        window.destroyed.connect(lambda _=None, view=window: self._forget_reconstruction_window(view))
        self._reconstruction_windows.append(window)
        window.show()

    def _forget_reconstruction_window(self, window: QWidget) -> None:
        if window in self._reconstruction_windows:
            self._reconstruction_windows.remove(window)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        if hasattr(self, "_controls_frame"):
            self._controls_frame.setGeometry(12, 12, 280, 315)
        super().resizeEvent(event)

