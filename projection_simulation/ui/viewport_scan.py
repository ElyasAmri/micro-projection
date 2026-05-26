from __future__ import annotations

from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PySide6.QtCore import QElapsedTimer, QObject, Qt, QThread, Signal
from PySide6.QtGui import QImage
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QApplication

from ..core.constants import (
    SURFACE_CAMERA_CAPTURE_HEIGHT_PX,
    SURFACE_CAMERA_CAPTURE_WIDTH_PX,
    SWEEP_RECORD_FPS,
    SWEEP_RECORD_FRAMES,
    SWEEP_RECORD_HEIGHT,
    SWEEP_RECORD_PHASE_SPAN_DEG,
    SWEEP_RECORD_WIDTH,
)
from ..core.fringe import generate_fringe_image
from ..core.image_utils import even_video_frame, qimage_to_luma, qimage_to_rgb_array
from ..scanning.scan_pipeline import ScanReconstruction, reconstruct_from_phase_sequences


class _ViewportReconstructionWorker(QObject):
    """Runs the CPU-bound reconstruction off the GUI thread."""

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, window, reference_frames, object_frames, width, height) -> None:
        super().__init__()
        self._window = window
        self._reference_frames = reference_frames
        self._object_frames = object_frames
        self._width = width
        self._height = height

    def run(self) -> None:
        try:
            result = reconstruct_from_phase_sequences(
                self._window,
                self._reference_frames,
                self._object_frames,
                width=self._width,
                height=self._height,
            )
        except (RuntimeError, ValueError) as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)


class ViewportScanMixin:
    def reconstruct_current_object_from_viewport(
        self,
        *,
        width: int = SURFACE_CAMERA_CAPTURE_WIDTH_PX,
        height: int = SURFACE_CAMERA_CAPTURE_HEIGHT_PX,
        steps: int = 8,
        record_path: str | Path | None = None,
        fps: float = SWEEP_RECORD_FPS,
    ) -> ScanReconstruction:
        reference_frames, object_frames = self.capture_viewport_scan_sequences(
            width=width,
            height=height,
            steps=steps,
            record_path=record_path,
            fps=fps,
        )
        return reconstruct_from_phase_sequences(
            self,
            reference_frames,
            object_frames,
            width=width,
            height=height,
        )

    def capture_viewport_scan_sequences(
        self,
        *,
        width: int = SURFACE_CAMERA_CAPTURE_WIDTH_PX,
        height: int = SURFACE_CAMERA_CAPTURE_HEIGHT_PX,
        steps: int = 8,
        record_path: str | Path | None = None,
        fps: float = SWEEP_RECORD_FPS,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Capture the reference and object phase sequences on the GUI thread.

        Rendering uses the OpenGL context (GUI-thread only); the heavy
        reconstruction is split out so it can run on a worker thread.
        """
        if steps < 3:
            raise ValueError("At least three phase steps are required.")
        if width <= 0 or height <= 0:
            raise ValueError("Capture size must be positive.")
        if self.projection_source != "fringe":
            raise ValueError("Fringe source is required for viewport scanning.")

        previous_processed = self._processed
        previous_project_field_object = self.project_field_object
        previous_viewport_scan = getattr(self, "_viewport_scan_capture", False)
        controls_were_visible = (
            hasattr(self, "_controls_frame")
            and self._controls_frame.parent() is self
            and self._controls_frame.isVisible()
        )
        writer = None

        try:
            self._viewport_scan_capture = False
            if controls_were_visible:
                self._controls_frame.setVisible(False)

            if record_path is not None:
                destination = Path(record_path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                writer = imageio.get_writer(str(destination), fps=fps, macro_block_size=None)

            self.project_field_object = False
            reference_frames = self._capture_viewport_phase_sequence(
                width=width,
                height=height,
                steps=steps,
                phase_span_deg=SWEEP_RECORD_PHASE_SPAN_DEG,
                writer=writer,
                capture_surface_camera=True,
                preview_fps=fps,
            )

            self.project_field_object = previous_project_field_object
            object_frames = self._capture_viewport_phase_sequence(
                width=width,
                height=height,
                steps=steps,
                phase_span_deg=SWEEP_RECORD_PHASE_SPAN_DEG,
                writer=writer,
                capture_surface_camera=True,
                preview_fps=fps,
            )
        finally:
            if writer is not None:
                writer.close()
            self._viewport_scan_capture = previous_viewport_scan
            self.project_field_object = previous_project_field_object
            self._processed = previous_processed
            if controls_were_visible:
                self._controls_frame.setVisible(True)
            self.update()

        return reference_frames, object_frames

    def launch_viewport_reconstruction(
        self,
        reference_frames: np.ndarray,
        object_frames: np.ndarray,
        *,
        on_done,
        on_error,
    ) -> None:
        """Reconstruct on a worker thread so the GUI thread stays responsive."""
        height = int(object_frames.shape[1])
        width = int(object_frames.shape[2])
        thread = QThread(self)
        worker = _ViewportReconstructionWorker(self, reference_frames, object_frames, width, height)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        # on_done / on_error belong to the window (GUI thread), so AutoConnection
        # delivers them there even though the worker emits from its own thread.
        worker.finished.connect(on_done)
        worker.failed.connect(on_error)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_scan_thread)
        self._scan_thread = thread
        self._scan_worker = worker
        thread.start()

    def _clear_scan_thread(self) -> None:
        self._scan_thread = None
        self._scan_worker = None

    def _abort_scan_thread(self) -> None:
        thread = getattr(self, "_scan_thread", None)
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait()

    def record_viewport_sweep_video(
        self,
        output_path: str | Path,
        *,
        frames: int = SWEEP_RECORD_FRAMES,
        fps: float = SWEEP_RECORD_FPS,
        width: int = SWEEP_RECORD_WIDTH,
        height: int = SWEEP_RECORD_HEIGHT,
        phase_span_deg: float = SWEEP_RECORD_PHASE_SPAN_DEG,
    ) -> None:
        if frames <= 0:
            raise ValueError("Frames must be > 0.")
        if fps <= 0:
            raise ValueError("FPS must be > 0.")
        if width <= 0 or height <= 0:
            raise ValueError("Capture size must be positive.")
        if self.projection_source != "fringe":
            raise ValueError("Fringe source is required for sweep recording.")

        previous_processed = self._processed
        previous_viewport_scan = getattr(self, "_viewport_scan_capture", False)
        controls_were_visible = (
            hasattr(self, "_controls_frame")
            and self._controls_frame.parent() is self
            and self._controls_frame.isVisible()
        )
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        writer = None
        try:
            self._viewport_scan_capture = True
            if controls_were_visible:
                self._controls_frame.setVisible(False)
            writer = imageio.get_writer(str(destination), fps=fps, macro_block_size=None)
            self._capture_viewport_phase_sequence(
                width=width,
                height=height,
                steps=frames,
                phase_span_deg=phase_span_deg,
                writer=writer,
                capture_surface_camera=False,
                preview_fps=fps,
            )
        finally:
            if writer is not None:
                writer.close()
            self._viewport_scan_capture = previous_viewport_scan
            self._processed = previous_processed
            if controls_were_visible:
                self._controls_frame.setVisible(True)
            self.update()

    def _capture_viewport_phase_sequence(
        self,
        *,
        width: int,
        height: int,
        steps: int,
        phase_span_deg: float,
        writer,
        capture_surface_camera: bool,
        preview_fps: float,
    ) -> np.ndarray:
        frames: list[np.ndarray] = []
        denominator = max(1, steps - 1)
        source_phase = self.fringe_phase_deg
        for index in range(steps):
            frame_timer = QElapsedTimer()
            frame_timer.start()
            phase_deg = source_phase + (phase_span_deg * index / denominator)
            fringe = generate_fringe_image(
                self.fringe_width,
                self.fringe_height,
                period_px=self.fringe_period_px,
                phase_deg=phase_deg,
                orientation=self.fringe_orientation,
                contrast=self.fringe_contrast,
                bias=self.fringe_bias,
            )
            self._processed = self._process_image(fringe)
            self._refresh_live_viewport()
            frame = (
                self.render_surface_camera_telecentric_capture(width, height)
                if capture_surface_camera
                else self._grab_viewport_scan_frame(width, height)
            )
            if writer is not None:
                writer_frame = (
                    self._grab_viewport_scan_frame(width, height)
                    if capture_surface_camera
                    else frame
                )
                writer.append_data(qimage_to_rgb_array(even_video_frame(writer_frame)))
            frames.append(qimage_to_luma(frame))
            self._process_preview_events(frame_timer, preview_fps)
        return np.stack(frames, axis=0)

    def _refresh_live_viewport(self) -> None:
        self.update()
        QApplication.processEvents()
        self.repaint()
        QApplication.processEvents()

    def _process_preview_events(self, frame_timer: QElapsedTimer, fps: float) -> None:
        if fps <= 0:
            QApplication.processEvents()
            return
        target_ms = int(round(1000.0 / fps))
        while frame_timer.elapsed() < target_ms:
            remaining_ms = target_ms - frame_timer.elapsed()
            if remaining_ms > 1:
                QThread.msleep(min(10, remaining_ms))
            QApplication.processEvents()

    def _grab_viewport_scan_frame(self, width: int, height: int) -> QImage:
        if self.width() <= 0 or self.height() <= 0:
            self.resize(max(width, 2), max(height, 2))
        self.update()
        QApplication.processEvents()
        self.repaint()
        QApplication.processEvents()
        if isinstance(self, QOpenGLWidget):
            frame = self.grabFramebuffer()
        else:
            frame = self.grab().toImage()
        if frame.width() == width and frame.height() == height:
            return frame
        return frame.scaled(
            width,
            height,
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation,
        )

