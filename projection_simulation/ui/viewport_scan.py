from __future__ import annotations

from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PySide6.QtCore import QElapsedTimer, Qt, QThread
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

        return reconstruct_from_phase_sequences(
            self,
            reference_frames,
            object_frames,
            width=width,
            height=height,
        )

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

