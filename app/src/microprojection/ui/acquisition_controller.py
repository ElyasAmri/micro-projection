"""Coordinates acquisition pipelines.

Builds the right pipeline, runs it behind a modal progress dialog, and manages
the sidebar button lock and status reporting. Pulled out of MainWindow so the
capture-orchestration concern stands on its own.

It owns no hardware: it reaches the camera, the projector window, the camera
settings, and the current projection choice through the references and provider
callables it is handed (the latter are called fresh each run, since those values
change over the session). User-facing messages go out on ``status``.
"""
from __future__ import annotations

import os
import time

from PySide6.QtCore import QObject, Signal

from microprojection.pipelines import (
    AlignProjectionPipeline,
    FovPipeline,
    NoisePipeline,
    PhaseShiftPipeline,
)
from microprojection.ui.pipeline_progress_dialog import PipelineProgressDialog


class AcquisitionController(QObject):
    # user-facing status messages
    status = Signal(str)
    # horizontal viewing angle measured by the alignment pipeline, in degrees
    angleMeasured = Signal(float)

    def __init__(self, camera, sidebar, window, *,
                 projector_window, settings, projection, parent=None):
        super().__init__(parent)
        self._camera = camera
        self._sidebar = sidebar
        self._window = window  # QWidget parent for the modal dialog
        # Providers, re-read each run because these change over the session.
        self._get_projector_window = projector_window
        self._get_settings = settings
        self._get_projection = projection
        self._pipeline = None

    def run_phase_shift(self):
        """Project stepped fringes and capture one frame per phase."""
        projection = self._get_projection()
        pipeline = PhaseShiftPipeline(
            self._camera, self._get_projector_window(), self._get_settings(),
            self._capture_dir("phase_shift"),
            num_phases=8,
            period=projection.get("period", 32),
            orientation=projection.get("orientation", "vertical"),
            parent=self,
        )
        self._start(pipeline, "Phase-shift capture")

    def run_noise_test(self):
        """Capture many frames of a uniform flat field for noise analysis."""
        pipeline = NoisePipeline(
            self._camera, self._get_projector_window(), self._get_settings(),
            self._capture_dir("noise"),
            num_frames=1000,
            level=128,
            parent=self,
        )
        self._start(pipeline, "Noise test")

    def run_noise_fringe(self):
        """Like the noise test, but characterize noise under a sinusoidal fringe
        (the phase-shift operating condition) at the current projection's period
        and orientation."""
        projection = self._get_projection()
        pipeline = NoisePipeline(
            self._camera, self._get_projector_window(), self._get_settings(),
            self._capture_dir("noise_fringe"),
            num_frames=1000,
            pattern_kind="fringe",
            period=projection.get("period", 32),
            orientation=projection.get("orientation", "vertical"),
            parent=self,
        )
        self._start(pipeline, "Noise test (fringe)")

    def run_noise_dark(self):
        """Noise test with the projector black: the camera's own read noise and
        dark current, with no projected light to confound it."""
        pipeline = NoisePipeline(
            self._camera, self._get_projector_window(), self._get_settings(),
            self._capture_dir("noise_dark"),
            num_frames=1000,
            pattern_kind="dark",
            parent=self,
        )
        self._start(pipeline, "Noise test (dark frame)")

    def run_align(self):
        """Align the projection to the camera: clip, recenter on the crosshair,
        and stretch horizontally to undo the telecentric viewing angle."""
        pipeline = AlignProjectionPipeline(
            self._camera, self._get_projector_window(), self._get_settings(),
            self._capture_dir("align"),
            parent=self,
        )
        pipeline.angleMeasured.connect(self.angleMeasured)
        self._start(pipeline, "Align projection")

    def run_fov(self):
        """Project a box and shrink it to the camera frame to find the FOV."""
        pipeline = FovPipeline(
            self._camera, self._get_projector_window(), self._get_settings(),
            self._capture_dir("fov"),
            parent=self,
        )
        self._start(pipeline, "Camera FOV")

    def _capture_dir(self, label: str) -> str:
        """A fresh timestamped output directory under ./captures."""
        stamp = time.strftime("%Y%m%d_%H%M%S")
        return os.path.abspath(os.path.join("captures", f"{label}_{stamp}"))

    def _start(self, pipeline, title: str):
        if self._pipeline is not None and self._pipeline.running:
            self.status.emit("A capture is already running.")
            return
        self._pipeline = pipeline
        pipeline.status.connect(self.status)
        pipeline.finished.connect(self._on_finished)
        pipeline.failed.connect(self._on_failed)
        pipeline.cancelled.connect(self._end)
        self._sidebar.lock_acquisition()
        pipeline.start()
        # A precondition failure emits failed synchronously and is already
        # cleaned up; only show the progress modal for a run that started.
        if not pipeline.running:
            return
        dialog = PipelineProgressDialog(pipeline, title, self._window)
        dialog.exec()
        dialog.deleteLater()

    def _on_finished(self, out_dir: str):
        self.status.emit(f"Capture done. saved to {out_dir}")
        self._end()

    def _on_failed(self, message: str):
        self.status.emit(message)
        self._end()

    def _end(self):
        if self._pipeline is not None:
            self._pipeline.deleteLater()
            self._pipeline = None
        self._sidebar.refresh_acquisition_enabled()
