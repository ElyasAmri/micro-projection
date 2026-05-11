from __future__ import annotations

from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QApplication

from ..core.constants import (
    SWEEP_RECORD_FPS,
    SWEEP_RECORD_FRAMES,
    SWEEP_RECORD_HEIGHT,
    SWEEP_RECORD_PHASE_SPAN_DEG,
    SWEEP_RECORD_WIDTH,
)
from ..core.fringe import generate_fringe_image
from ..scanning.scan_pipeline import ScanReconstruction, reconstruct_from_phase_sequences


class ViewportScanMixin:
    def reconstruct_current_object_from_viewport(
        self,
        *,
        width: int = 192,
        height: int = 108,
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
            hasattr(self, "_controls_frame") and self._controls_frame.isVisible()
        )
        writer = None

        try:
            self._viewport_scan_capture = True
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
            )

            self.project_field_object = previous_project_field_object
            object_frames = self._capture_viewport_phase_sequence(
                width=width,
                height=height,
                steps=steps,
                phase_span_deg=SWEEP_RECORD_PHASE_SPAN_DEG,
                writer=writer,
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
            hasattr(self, "_controls_frame") and self._controls_frame.isVisible()
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
    ) -> np.ndarray:
        frames: list[np.ndarray] = []
        denominator = max(1, steps - 1)
        source_phase = self.fringe_phase_deg
        for index in range(steps):
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
            frame = self._grab_viewport_scan_frame(width, height)
            if writer is not None:
                writer.append_data(self._qimage_to_rgb_array(_even_video_frame(frame)))
            frames.append(_qimage_to_luma(frame))
        return np.stack(frames, axis=0)

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


def _qimage_to_luma(image: QImage) -> np.ndarray:
    rgb = image.convertToFormat(QImage.Format_RGB888)
    width = rgb.width()
    height = rgb.height()
    row_stride = rgb.bytesPerLine()
    buffer = np.frombuffer(rgb.bits(), dtype=np.uint8).reshape((height, row_stride))
    pixels = buffer[:, : width * 3].reshape((height, width, 3))
    return pixels.astype(np.float64).mean(axis=2) / 255.0


def _even_video_frame(image: QImage) -> QImage:
    width = image.width() if image.width() % 2 == 0 else image.width() + 1
    height = image.height() if image.height() % 2 == 0 else image.height() + 1
    if width == image.width() and height == image.height():
        return image
    return image.scaled(width, height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
