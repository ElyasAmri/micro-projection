import math
import os
from pathlib import Path
from collections.abc import Callable

from PySide6.QtCore import QPointF, Qt, Slot
from PySide6.QtGui import (
    QCloseEvent,
    QImage,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPixmap,
    QShortcut,
    QSurfaceFormat,
    QTransform,
    QWheelEvent,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget

from ..core.constants import DEFAULT_DEVICE_SPACING_CM
from ..core.profiling import FrameProfiler
from ..core.types import CameraContext, Vec3
from ..geometry.camera_navigation import CameraNavigationMixin
from ..geometry.optics_geometry import OpticsGeometryMixin
from ..rendering.device_rendering import DeviceRenderingMixin
from ..rendering.grid_rendering import GridRenderingMixin
from ..rendering.opengl_renderer import OpenGLProjectionRenderer
from ..rendering.projection_mapping import ProjectionMappingMixin
from ..rendering.scene_assembly import SceneAssemblyMixin
from .controls import ProjectionControlsMixin
from .surface_camera import SurfaceCameraMixin
from .viewport_scan import ViewportScanMixin

RenderWidgetBase = (
    QWidget
    if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
    else QOpenGLWidget
)


class ProjectionWindow(
    ProjectionControlsMixin,
    DeviceRenderingMixin,
    GridRenderingMixin,
    SceneAssemblyMixin,
    CameraNavigationMixin,
    OpticsGeometryMixin,
    ProjectionMappingMixin,
    SurfaceCameraMixin,
    ViewportScanMixin,
    RenderWidgetBase,
):
    def __init__(
        self,
        image: QImage,
        *,
        mode: str,
        fill: bool,
        fullscreen: bool,
        force_landscape: bool,
        mirror_horizontal: bool,
        fov_deg: float,
        projector_fov_deg: float | None,
        distance_m: float,
        use_axis_distance: bool,
        projector_x: float,
        projector_y: float,
        projector_z: float,
        main_camera_x: float,
        main_camera_y: float,
        main_camera_z: float,
        plane_center_x: float,
        plane_center_y: float,
        plane_center_z: float,
        plane_width_m: float,
        plane_height_m: float,
        project_projection_plane: bool,
        project_field_object: bool,
        field_center_x: float,
        field_center_y: float,
        field_center_z: float,
        field_width_m: float,
        field_height_m: float,
        projector_axis: str,
        camera_x: float,
        camera_y: float,
        camera_z: float,
        show_ground_grid: bool,
        grid_step: float,
        grid_extent: float,
        grid_major_every: int,
        projector_lens_offset_x: float,
        projector_lens_offset_y: float,
        projector_lens_offset_z: float,
        yaw_deg: float,
        pitch_deg: float,
        roll_deg: float,
    ) -> None:
        super().__init__()
        if isinstance(self, QOpenGLWidget):
            surface_format = QSurfaceFormat()
            surface_format.setRenderableType(QSurfaceFormat.OpenGL)
            surface_format.setProfile(QSurfaceFormat.CompatibilityProfile)
            surface_format.setVersion(2, 1)
            surface_format.setDepthBufferSize(24)
            surface_format.setSamples(4)
            self.setFormat(surface_format)
        self.mode = mode
        self.fill = fill
        self.fullscreen = fullscreen
        self.force_landscape = force_landscape
        self.mirror_horizontal = mirror_horizontal
        self.fov_deg = fov_deg
        self.projector_fov_deg = projector_fov_deg
        self.use_axis_distance = use_axis_distance
        self.projector_x = projector_x
        self.projector_y = projector_y
        self.projector_z = projector_z
        self.main_camera_x = main_camera_x
        self.main_camera_y = main_camera_y
        self.main_camera_z = main_camera_z
        self.plane_center_x = plane_center_x
        self.plane_center_y = plane_center_y
        self.plane_center_z = plane_center_z
        self.plane_width_m = plane_width_m
        self.plane_height_m = plane_height_m
        self.project_projection_plane = project_projection_plane
        self.project_field_object = project_field_object
        self.field_object_kind = "box"
        self.field_center_x = field_center_x
        self.field_center_y = field_center_y
        self.field_center_z = field_center_z
        self.field_width_m = field_width_m
        self.field_height_m = field_height_m
        self.projector_axis = projector_axis
        self.camera_x = camera_x
        self.camera_y = camera_y
        self.camera_z = camera_z
        self.show_ground_grid = show_ground_grid
        self.grid_step = grid_step
        self.grid_extent = grid_extent
        self.grid_major_every = grid_major_every
        self.projector_lens_offset_x = projector_lens_offset_x
        self.projector_lens_offset_y = projector_lens_offset_y
        self.projector_lens_offset_z = projector_lens_offset_z
        self.yaw_deg = yaw_deg
        self.pitch_deg = pitch_deg
        self.roll_deg = roll_deg
        self._default_projector_fov_deg = self._compute_default_projector_fov_deg()
        self._base_plane_center = self._resolve_base_plane_center(distance_m)
        self._symmetry_normal, self._symmetry_tangent = self._derive_symmetry_basis()
        self._projection_angle_deg, self.distance_m = self._derive_initial_projection_geometry(
            distance_m
        )
        self._device_distance_m = self.distance_m
        self._device_lateral_sign = -1.0 if self._projection_angle_deg < 0.0 else 1.0
        self._device_spacing_cm = DEFAULT_DEVICE_SPACING_CM
        self._base_distance_m = self.distance_m
        self._default_device_spacing_cm = self._device_spacing_cm
        self._default_distance_m = self.distance_m
        self._default_projector_fov_setting = self.projector_fov_deg
        self._projector_pos: Vec3 = (self.projector_x, self.projector_y, self.projector_z)
        self._surface_camera_pos: Vec3 = (
            self.main_camera_x,
            self.main_camera_y,
            self.main_camera_z,
        )
        # Move plane on one fixed axis away from both devices (midpoint -> plane direction).
        self._plane_shift_direction = (
            -self._symmetry_normal[0],
            -self._symmetry_normal[1],
            -self._symmetry_normal[2],
        )
        self._update_reflected_devices()
        self._processed = self._process_image(image)
        self.projection_source = "fringe"
        self.fringe_width = self._processed.width()
        self.fringe_height = self._processed.height()
        self.fringe_period_px = 48.0
        self.fringe_phase_deg = 0.0
        self.fringe_orientation = "vertical"
        self.fringe_contrast = 1.0
        self.fringe_bias = 0.5
        self._reload_handler: Callable[[], None] | None = None
        self._recording_video = False
        self._scan_in_progress = False
        self._viewport_scan_capture = False
        self._reconstruction_windows: list[QWidget] = []
        self._profiler = FrameProfiler(
            Path(os.environ.get("PROJECTION_SIM_PERF_LOG", "projection-sim-performance.log"))
        )
        self._gpu_renderer: OpenGLProjectionRenderer | None = None
        self._orbit_target: Vec3 = (0.0, 0.0, 0.0)
        self._orbit_dragging = False
        self._orbit_last_pos: QPointF | None = None
        self._orbit_rotate_speed = 0.008
        self._orbit_zoom_speed = 0.15
        self._sync_orbit_from_camera()

        self.setWindowTitle("Projection Window")
        if self.fullscreen:
            self.setWindowFlag(Qt.FramelessWindowHint, True)
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setStyleSheet("background-color: black;")
        self.setFocusPolicy(Qt.StrongFocus)
        self._init_controls()
        self._init_shortcuts()

    def _process_image(self, image: QImage) -> QImage:
        processed = image
        if self.force_landscape and processed.height() > processed.width():
            processed = processed.transformed(QTransform().rotate(90))
        if self.mirror_horizontal:
            processed = processed.mirrored(True, False)
        return processed

    def configure_projection_source(
        self,
        *,
        source: str,
        fringe_width: int,
        fringe_height: int,
        fringe_period_px: float,
        fringe_phase_deg: float,
        fringe_orientation: str,
        fringe_contrast: float,
        fringe_bias: float,
    ) -> None:
        self.projection_source = source
        self.fringe_width = fringe_width
        self.fringe_height = fringe_height
        self.fringe_period_px = fringe_period_px
        self.fringe_phase_deg = fringe_phase_deg
        self.fringe_orientation = fringe_orientation
        self.fringe_contrast = fringe_contrast
        self.fringe_bias = fringe_bias
        if hasattr(self, "_record_sweep_button"):
            self._refresh_control_labels()

    def set_reload_handler(self, handler: Callable[[], None] | None) -> None:
        self._reload_handler = handler

    def _init_shortcuts(self) -> None:
        self._reload_shortcut_r = QShortcut(QKeySequence("R"), self)
        self._reload_shortcut_r.setContext(Qt.WidgetWithChildrenShortcut)
        self._reload_shortcut_r.activated.connect(lambda: self._trigger_reload("shortcut:R"))
        self._reload_shortcut_ctrl_r = QShortcut(QKeySequence("Ctrl+R"), self)
        self._reload_shortcut_ctrl_r.setContext(Qt.WidgetWithChildrenShortcut)
        self._reload_shortcut_ctrl_r.activated.connect(
            lambda: self._trigger_reload("shortcut:Ctrl+R")
        )
        self._reload_shortcut_f5 = QShortcut(QKeySequence("F5"), self)
        self._reload_shortcut_f5.setContext(Qt.WidgetWithChildrenShortcut)
        self._reload_shortcut_f5.activated.connect(lambda: self._trigger_reload("shortcut:F5"))

    def _log_reload_debug(self, message: str) -> None:
        print(f"[reload-debug] {message}", flush=True)

    def _begin_perf_frame(self, label: str) -> None:
        self._profiler.begin_frame(label)

    def _record_perf(self, name: str, duration_s: float) -> None:
        self._profiler.record(name, duration_s)

    def _profile_section(self, name: str):
        return self._profiler.section(name)

    def _end_perf_frame(self) -> None:
        self._profiler.end_frame()

    @Slot()
    def _trigger_reload(self, source: str = "unknown") -> None:
        self._log_reload_debug(
            f"reload trigger source={source}, handler={'set' if self._reload_handler else 'missing'}"
        )
        if self._reload_handler is not None:
            self._reload_handler()



    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        self._log_reload_debug(
            "keyPressEvent "
            f"key={event.key()} text={event.text()!r} mods={int(event.modifiers())} "
            f"focus={type(self.focusWidget()).__name__ if self.focusWidget() is not None else 'None'}"
        )
        if event.key() == Qt.Key_Escape:
            self._log_reload_debug("closing window via Escape")
            self.close()
            return
        if event.key() == Qt.Key_R:
            self._trigger_reload("keyPressEvent:R")
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        self._log_reload_debug("closeEvent received")
        if isinstance(self, QOpenGLWidget) and self._gpu_renderer is not None:
            self.makeCurrent()
            self._gpu_renderer.dispose()
            self._gpu_renderer = None
            self.doneCurrent()
        super().closeEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self.mode == "plane3d" and event.button() == Qt.LeftButton:
            self._orbit_dragging = True
            self._orbit_last_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self.mode == "plane3d" and self._orbit_dragging and self._orbit_last_pos is not None:
            current = event.position()
            dx = current.x() - self._orbit_last_pos.x()
            dy = current.y() - self._orbit_last_pos.y()
            self._orbit_last_pos = current

            self._orbit_azimuth -= dx * self._orbit_rotate_speed
            self._orbit_elevation += dy * self._orbit_rotate_speed
            elevation_limit = math.radians(89.0)
            self._orbit_elevation = max(
                -elevation_limit, min(elevation_limit, self._orbit_elevation)
            )

            self._apply_orbit_to_camera()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self.mode == "plane3d" and event.button() == Qt.LeftButton:
            self._orbit_dragging = False
            self._orbit_last_pos = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # type: ignore[override]
        if self.mode == "plane3d":
            steps = event.angleDelta().y() / 120.0
            if steps != 0:
                zoom_scale = math.exp(-steps * self._orbit_zoom_speed)
                self._orbit_radius = max(0.2, min(5000.0, self._orbit_radius * zoom_scale))
                self._apply_orbit_to_camera()
                self.update()
            event.accept()
            return
        super().wheelEvent(event)

    def initializeGL(self) -> None:  # type: ignore[override]
        self._gpu_renderer = OpenGLProjectionRenderer()
        self._gpu_renderer.initialize()

    def paintGL(self) -> None:  # type: ignore[override]
        self._begin_perf_frame("paintGL")
        try:
            with self._profile_section("gpu_scene_build"):
                scene = self._build_projection_scene(self.width(), self.height(), include_minimap=True)
            if scene is None:
                return
            if self._gpu_renderer is None:
                self._gpu_renderer = OpenGLProjectionRenderer()
                self._gpu_renderer.initialize()
            with self._profile_section("gpu_render"):
                self._gpu_renderer.render(
                    scene,
                    self.width(),
                    self.height(),
                    device_pixel_ratio=self.devicePixelRatioF(),
                )
            if not self._viewport_scan_capture:
                with self._profile_section("gpu_qpainter_overlay"):
                    painter = QPainter(self)
                    painter.setRenderHint(QPainter.Antialiasing, True)
                    pixmap = QPixmap.fromImage(self._processed)
                    self._draw_scene_surface_wireframes(painter, self.width(), self.height())
                    self._draw_projector_contours(
                        painter,
                        pixmap,
                        self.width(),
                        self.height(),
                    )
                    self._draw_surface_camera_minimap_chrome(painter)
                    painter.end()
        finally:
            self._end_perf_frame()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        if isinstance(self, QOpenGLWidget):
            super().paintEvent(event)
            return
        self._begin_perf_frame("paintEvent")
        try:
            with self._profile_section("paintEvent"):
                painter = QPainter(self)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.fillRect(self.rect(), Qt.black)

                pixmap = QPixmap.fromImage(self._processed)
                if self._viewport_scan_capture:
                    capture = self.render_surface_camera_telecentric_capture(
                        max(2, self.width()),
                        max(2, self.height()),
                    )
                    painter.drawImage(self.rect(), capture)
                    return
                if self.mode == "plane3d":
                    projector_context = self._projector_projection_context(
                        pixmap.width(),
                        pixmap.height(),
                    )
                    scene_surfaces = self._scene_surfaces()
                    if self.show_ground_grid:
                        with self._profile_section("_draw_ground_grid"):
                            self._draw_ground_grid(painter, self.width(), self.height())
                    with self._profile_section("_draw_plane3d_projection"):
                        drew_projection = self._draw_plane3d_projection(
                            painter,
                            pixmap,
                            projector_context=projector_context,
                            scene_surfaces=scene_surfaces,
                        )
                    with self._profile_section("_draw_projector_contours"):
                        self._draw_projector_contours(
                            painter,
                            pixmap,
                            self.width(),
                            self.height(),
                        )
                    with self._profile_section("_draw_surface_camera_minimap"):
                        self._draw_surface_camera_minimap(
                            painter,
                            pixmap,
                            projector_context=projector_context,
                            scene_surfaces=scene_surfaces,
                        )
                    if drew_projection:
                        return

                with self._profile_section("_draw_scaled_fit"):
                    self._draw_scaled_fit(painter, pixmap)
        finally:
            self._end_perf_frame()
