from __future__ import annotations

import math
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from ..core.constants import (
    MINIMAP_RAYCAST_COLUMNS,
    MINIMAP_RAYCAST_EDGE_SUBDIVISIONS,
    MINIMAP_RAYCAST_ROWS,
    SWEEP_RECORD_FPS,
    SWEEP_RECORD_FRAMES,
    SWEEP_RECORD_HEIGHT,
    SWEEP_RECORD_PHASE_SPAN_DEG,
    SWEEP_RECORD_WIDTH,
)
from ..core.fringe import generate_fringe_image
from ..core.math3d import vec_cross, vec_dot, vec_normalize, vec_subtract
from ..core.types import Vec3
from ..rendering.opengl_renderer import OpenGLProjectionRenderer

SceneSurface = tuple[str, list[Vec3], QColor]
TelecentricScanContext = tuple[Vec3, Vec3, Vec3, Vec3, float, float]


class SurfaceCameraMixin:
    def _surface_camera_telecentric_scan_context(
        self,
        image_width: int,
        image_height: int,
    ) -> TelecentricScanContext | None:
        if image_width <= 0 or image_height <= 0:
            return None
        telecentric_origin = self._surface_telecentric_lens_center_world()
        if telecentric_origin is None:
            return None
        forward = self._horizontal_forward_direction(telecentric_origin)
        world_up: Vec3 = (0.0, 0.0, 1.0)
        if abs(vec_dot(forward, world_up)) > 0.98:
            world_up = (0.0, 1.0, 0.0)
        right = vec_normalize(vec_cross(forward, world_up))
        if right is None:
            return None
        up = vec_cross(right, forward)

        primary_surface = self._primary_projection_surface()
        target_center = primary_surface[0] if primary_surface is not None else self._look_target()
        target_depth = vec_dot(vec_subtract(target_center, telecentric_origin), forward)
        if target_depth <= 1e-5:
            target_depth = max(1.0, self.distance_m)
        half_h = target_depth * math.tan(math.radians(self._effective_projector_fov_deg()) / 2.0)
        half_w = half_h * (float(image_width) / float(image_height))
        return (telecentric_origin, right, up, forward, half_w, half_h)

    def _surface_camera_projection_context(
        self, image_width: int, image_height: int
    ) -> tuple[Vec3, Vec3, Vec3, Vec3, float, float] | None:
        if image_width <= 0 or image_height <= 0:
            return None
        telecentric_origin = self._surface_telecentric_lens_center_world()
        if telecentric_origin is None:
            return None
        forward = self._horizontal_forward_direction(telecentric_origin)
        world_up: Vec3 = (0.0, 0.0, 1.0)
        if abs(vec_dot(forward, world_up)) > 0.98:
            world_up = (0.0, 1.0, 0.0)
        right = vec_normalize(vec_cross(forward, world_up))
        if right is None:
            return None
        up = vec_cross(right, forward)
        aspect = float(image_width) / float(image_height)
        tan_half_fov = math.tan(math.radians(self._effective_projector_fov_deg()) / 2.0)
        return (telecentric_origin, right, up, forward, tan_half_fov, aspect)

    @staticmethod
    def _qimage_to_rgb_array(image: QImage) -> np.ndarray:
        rgb = image.convertToFormat(QImage.Format_RGB888)
        width = rgb.width()
        height = rgb.height()
        row_stride = rgb.bytesPerLine()
        buffer = np.frombuffer(rgb.bits(), dtype=np.uint8).reshape((height, row_stride))
        return buffer[:, : width * 3].reshape((height, width, 3)).copy()

    def record_surface_camera_sweep_video(
        self,
        output_path: str,
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

        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        denominator = max(1, frames - 1)
        source_phase = self.fringe_phase_deg
        previous_processed = self._processed

        try:
            with imageio.get_writer(str(destination), fps=fps, macro_block_size=None) as writer:
                for frame_index in range(frames):
                    phase_deg = source_phase + (phase_span_deg * frame_index / denominator)
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
                    capture = self.render_surface_camera_telecentric_capture(width, height)
                    writer.append_data(self._qimage_to_rgb_array(capture))
        finally:
            self._processed = previous_processed
            self.update()

    def render_surface_camera_capture(self, width: int, height: int) -> QImage:
        gpu_capture = self._render_surface_camera_capture_gpu(
            max(2, width),
            max(2, height),
        )
        if gpu_capture is not None:
            return gpu_capture

        pixmap = QPixmap.fromImage(self._processed)
        capture, _ = self._render_surface_camera_capture(
            pixmap,
            max(2, width),
            max(2, height),
        )
        return capture

    def render_surface_camera_telecentric_capture(self, width: int, height: int) -> QImage:
        width = max(2, width)
        height = max(2, height)
        gpu_capture = self._render_surface_camera_telecentric_capture_gpu(width, height)
        if gpu_capture is not None:
            return gpu_capture
        return self._render_surface_camera_telecentric_capture_cpu(
            QPixmap.fromImage(self._processed),
            width,
            height,
        )

    def _render_surface_camera_capture_gpu(self, width: int, height: int) -> QImage | None:
        if not isinstance(self, QOpenGLWidget):
            return None
        if self.context() is None:
            return None
        view_context = self._surface_camera_view_context(width, height)
        if view_context is None:
            return None

        self.makeCurrent()
        try:
            if self._gpu_renderer is None:
                self._gpu_renderer = OpenGLProjectionRenderer()
                self._gpu_renderer.initialize()
            scene = self._build_projection_scene(
                width,
                height,
                include_minimap=False,
                include_grid=False,
            )
            if scene is None:
                return None
            view = self._camera_view_from_context(
                view_context,
                self._effective_projector_fov_deg(),
            )
            with self._profile_section("gpu_surface_camera_capture"):
                return self._gpu_renderer.render_view_to_image(scene, view, width, height)
        finally:
            self.doneCurrent()

    def _render_surface_camera_telecentric_capture_gpu(
        self,
        width: int,
        height: int,
    ) -> QImage | None:
        if not isinstance(self, QOpenGLWidget):
            return None
        if self.context() is None:
            return None
        scan_context = self._surface_camera_telecentric_scan_context(width, height)
        if scan_context is None:
            return None

        self.makeCurrent()
        try:
            if self._gpu_renderer is None:
                self._gpu_renderer = OpenGLProjectionRenderer()
                self._gpu_renderer.initialize()
            scene = self._build_projection_scene(
                width,
                height,
                include_minimap=False,
                include_grid=False,
            )
            if scene is None:
                return None
            view = self._telecentric_camera_view_from_context(scan_context)
            with self._profile_section("gpu_surface_camera_telecentric_capture"):
                return self._gpu_renderer.render_view_to_image(scene, view, width, height)
        finally:
            self.doneCurrent()

    def _render_surface_camera_telecentric_capture_cpu(
        self,
        pixmap: QPixmap,
        width: int,
        height: int,
    ) -> QImage:
        with self._profile_section("_render_surface_camera_telecentric_capture_cpu"):
            capture = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
            capture.fill(QColor(8, 10, 14))
            source_image = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
            scan_context = self._surface_camera_telecentric_scan_context(width, height)
            projector_context = self._projector_projection_context(
                source_image.width(),
                source_image.height(),
            )
            projection_scan_context = self._surface_camera_telecentric_scan_context(
                source_image.width(),
                source_image.height(),
            )
            fringe_context = (
                self._primary_surface_fringe_context(
                    source_image.width(),
                    source_image.height(),
                    projection_scan_context,
                )
                if self.projection_source == "fringe"
                else None
            )
            scene_surfaces = self._scene_surfaces()
            if (
                scan_context is None
                or projector_context is None
                or not scene_surfaces
            ):
                return capture

            max_source_x = source_image.width() - 1
            max_source_y = source_image.height() - 1
            for y in range(height):
                for x in range(width):
                    hit = self._first_telecentric_scan_hit(
                        x + 0.5,
                        y + 0.5,
                        width,
                        height,
                        scan_context,
                        scene_surfaces,
                    )
                    if hit is None:
                        continue
                    surface_index, hit_world = hit
                    color = QColor(scene_surfaces[surface_index][2])
                    source_point: QPointF | None = None
                    if fringe_context is not None:
                        source_point = self._fringe_source_point_for_projector_ray(
                            hit_world,
                            projector_context,
                            fringe_context,
                            source_image.width(),
                            source_image.height(),
                        )
                    elif self._world_point_inside_projection_context(
                        hit_world,
                        projection_scan_context,
                    ):
                        source_point = self._projector_source_point_for_world(
                            hit_world,
                            projector_context,
                            source_image.width(),
                            source_image.height(),
                        )
                    if source_point is not None:
                        sx = max(0, min(max_source_x, int(source_point.x())))
                        sy = max(0, min(max_source_y, int(source_point.y())))
                        color = source_image.pixelColor(sx, sy)
                    capture.setPixelColor(x, y, color)
            return capture

    def _render_surface_camera_capture(
        self,
        pixmap: QPixmap,
        width: int,
        height: int,
        *,
        projector_context: tuple[Vec3, Vec3, Vec3, Vec3, float, float] | None = None,
        scene_surfaces: list[SceneSurface] | None = None,
        draw_crosshair: bool = False,
    ) -> tuple[QImage, bool]:
        capture = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        capture.fill(QColor(8, 10, 14))
        view_context = self._surface_camera_view_context(width, height)
        out_of_frame = view_context is None

        capture_painter = QPainter(capture)
        capture_painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        capture_painter.setRenderHint(QPainter.Antialiasing, True)
        if view_context is not None:
            if not self._draw_projected_scene(
                capture_painter,
                pixmap,
                width,
                height,
                view_context=view_context,
                columns=MINIMAP_RAYCAST_COLUMNS,
                rows=MINIMAP_RAYCAST_ROWS,
                edge_subdivisions=MINIMAP_RAYCAST_EDGE_SUBDIVISIONS,
                projector_context=projector_context,
                scene_surfaces=scene_surfaces,
            ):
                out_of_frame = True
            if draw_crosshair:
                cx = width // 2
                cy = height // 2
                capture_painter.setPen(QPen(QColor(220, 230, 250, 130), 1))
                capture_painter.drawLine(cx - 7, cy, cx + 7, cy)
                capture_painter.drawLine(cx, cy - 7, cx, cy + 7)
        capture_painter.end()
        return (capture, out_of_frame)

    def _draw_surface_camera_minimap(
        self,
        painter: QPainter,
        pixmap: QPixmap,
        *,
        projector_context: tuple[Vec3, Vec3, Vec3, Vec3, float, float] | None = None,
        scene_surfaces: list[SceneSurface] | None = None,
    ) -> None:
        inset_margin = 12
        inset_width = max(220, min(360, int(self.width() * 0.30)))
        inset_height = max(140, int(inset_width * 9.0 / 16.0))
        if inset_height > self.height() - inset_margin * 2:
            inset_height = max(120, self.height() - inset_margin * 2)
            inset_width = max(180, int(inset_height * 16.0 / 9.0))

        inset_x = self.width() - inset_width - inset_margin
        inset_y = inset_margin
        painter.save()
        painter.setPen(QPen(QColor(190, 200, 220, 220), 1))
        painter.setBrush(QColor(10, 12, 18, 215))
        painter.drawRect(inset_x, inset_y, inset_width, inset_height)
        painter.restore()

        render_width = max(2, inset_width - 2)
        render_height = max(2, inset_height - 2)
        minimap, out_of_frame = self._render_surface_camera_capture(
            pixmap,
            render_width,
            render_height,
            projector_context=projector_context,
            scene_surfaces=scene_surfaces,
            draw_crosshair=True,
        )

        painter.drawImage(inset_x + 1, inset_y + 1, minimap)
        painter.save()
        if out_of_frame:
            painter.setPen(QColor(255, 210, 210, 230))
            painter.drawText(inset_x + 8, inset_y + 32, "OUT OF FRAME")

        painter.setPen(QColor(220, 230, 245, 220))
        painter.drawText(inset_x + 8, inset_y + 16, "Surface Camera Capture")
        painter.restore()
