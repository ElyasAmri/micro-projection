import math
import os
from pathlib import Path
from collections.abc import Callable

import imageio.v2 as imageio
import numpy as np

from PySide6.QtCore import QPointF, Qt, Slot
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QImage,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QShortcut,
    QTransform,
    QWheelEvent,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QFrame, QLabel, QSlider, QVBoxLayout, QWidget
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton

from .fringe import generate_fringe_image
from .math3d import vec_cross, vec_dot, vec_normalize, vec_subtract
from .types import CameraContext, Vec3

PROJECTOR_THROW_RATIO = 1.2
PROJECTOR_IMAGE_ASPECT = 16.0 / 9.0
PROJECTOR_ANGLE_LIMIT_DEG = 45
DEFAULT_PROJECTION_ANGLE_DEG = -20.0
DEFAULT_DEVICE_SPACING_CM = 12.0
PROJECTOR_LENS_WINDOW_WIDTH_CM = 1.4
PROJECTOR_LENS_WINDOW_HEIGHT_CM = 1.0
PROJECTOR_LENS_FACE_EPS = 0.01
SURFACE_CAMERA_LENS_HEIGHT_CM = 8.1
TELECENTRIC_LENS_DIAMETER_CM = 3.6
TELECENTRIC_LENS_TO_CAMERA_LENS_CM = 4.0
SURFACE_CAMERA_REAR_LENS_DIAMETER_CM = 1.6
PROJECTOR_RAYCAST_COLUMNS = 12
PROJECTOR_RAYCAST_ROWS = 8
PROJECTOR_RAYCAST_EDGE_SUBDIVISIONS = 2
MINIMAP_RAYCAST_COLUMNS = 6
MINIMAP_RAYCAST_ROWS = 4
MINIMAP_RAYCAST_EDGE_SUBDIVISIONS = 1
FIELD_OBJECT_PLANE_GAP_M = 0.2
SWEEP_RECORD_FRAMES = 60
SWEEP_RECORD_FPS = 20.0
SWEEP_RECORD_WIDTH = 640
SWEEP_RECORD_HEIGHT = 360
SWEEP_RECORD_PHASE_SPAN_DEG = 360.0
SceneSurface = tuple[str, list[Vec3], QColor]
TelecentricScanContext = tuple[Vec3, Vec3, Vec3, Vec3, float, float]
FringeRectContext = tuple[Vec3, Vec3, Vec3, Vec3, float, float, float, float]
RenderWidgetBase = (
    QWidget
    if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
    else QOpenGLWidget
)


class ProjectionWindow(RenderWidgetBase):
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

    @Slot()
    def _trigger_reload(self, source: str = "unknown") -> None:
        self._log_reload_debug(
            f"reload trigger source={source}, handler={'set' if self._reload_handler else 'missing'}"
        )
        if self._reload_handler is not None:
            self._reload_handler()

    def _resolve_base_plane_center(self, distance_m: float) -> Vec3:
        if self.use_axis_distance:
            if self.projector_axis == "y":
                return (
                    self.projector_x,
                    self.projector_y + distance_m,
                    self.projector_z,
                )
            return (
                self.projector_x,
                self.projector_y,
                self.projector_z + distance_m,
            )
        return (
            self.plane_center_x,
            self.plane_center_y,
            self.plane_center_z,
        )

    def _derive_symmetry_basis(self) -> tuple[Vec3, Vec3]:
        center = self._base_plane_center
        projector = (self.projector_x, self.projector_y, self.projector_z)
        surface_camera = (self.main_camera_x, self.main_camera_y, self.main_camera_z)
        midpoint = (
            (projector[0] + surface_camera[0]) * 0.5,
            (projector[1] + surface_camera[1]) * 0.5,
            (projector[2] + surface_camera[2]) * 0.5,
        )

        normal = vec_normalize(vec_subtract(midpoint, center))
        if normal is None:
            normal = vec_normalize(vec_subtract(projector, center))
        if normal is None:
            normal = (0.0, -1.0, 0.0) if self.projector_axis == "y" else (0.0, 0.0, -1.0)

        tangent_raw = vec_subtract(surface_camera, projector)
        tangent_planar = (
            tangent_raw[0] - normal[0] * vec_dot(tangent_raw, normal),
            tangent_raw[1] - normal[1] * vec_dot(tangent_raw, normal),
            tangent_raw[2] - normal[2] * vec_dot(tangent_raw, normal),
        )
        tangent = vec_normalize(tangent_planar)
        if tangent is None:
            world_up: Vec3 = (0.0, 0.0, 1.0)
            tangent = vec_normalize(vec_cross(world_up, normal))
        if tangent is None:
            tangent = (1.0, 0.0, 0.0)
        return (normal, tangent)

    def _derive_initial_projection_geometry(
        self, configured_distance_cm: float
    ) -> tuple[float, float]:
        angle = max(
            -float(PROJECTOR_ANGLE_LIMIT_DEG),
            min(float(PROJECTOR_ANGLE_LIMIT_DEG), DEFAULT_PROJECTION_ANGLE_DEG),
        )
        return (angle, max(0.2, configured_distance_cm))

    def _spacing_from_angle(self, angle_deg: float, radius_cm: float) -> float:
        if radius_cm <= 1e-9:
            return 0.0
        return abs(2.0 * radius_cm * math.sin(math.radians(angle_deg)))

    def _clamp_aperture_center_world(self, origin: Vec3) -> Vec3 | None:
        forward = self._horizontal_forward_direction(origin)
        world_up: Vec3 = (0.0, 0.0, 1.0)
        if abs(vec_dot(forward, world_up)) > 0.98:
            world_up = (0.0, 1.0, 0.0)
        right = vec_normalize(vec_cross(world_up, forward))
        if right is None:
            return None
        up = vec_cross(forward, right)
        if abs(up[2]) <= 1e-6:
            return None
        ground_align_local_y = -origin[2] / up[2]
        hole_center_y = SURFACE_CAMERA_LENS_HEIGHT_CM
        return (
            origin[0] + up[0] * (hole_center_y + ground_align_local_y),
            origin[1] + up[1] * (hole_center_y + ground_align_local_y),
            origin[2] + up[2] * (hole_center_y + ground_align_local_y),
        )

    def _surface_telecentric_lens_center_world(self) -> Vec3 | None:
        return self._clamp_aperture_center_world(self._surface_camera_pos)

    def _surface_camera_lens_centers_world(self) -> tuple[Vec3, Vec3, Vec3] | None:
        telecentric_center = self._surface_telecentric_lens_center_world()
        if telecentric_center is None:
            return None
        forward = self._horizontal_forward_direction(telecentric_center)
        camera_lens_center = (
            telecentric_center[0] - forward[0] * TELECENTRIC_LENS_TO_CAMERA_LENS_CM,
            telecentric_center[1] - forward[1] * TELECENTRIC_LENS_TO_CAMERA_LENS_CM,
            telecentric_center[2] - forward[2] * TELECENTRIC_LENS_TO_CAMERA_LENS_CM,
        )
        return (telecentric_center, camera_lens_center, forward)

    def _ray_origins_world(self) -> tuple[Vec3, Vec3] | None:
        lens_data = self._projector_lens_rectangle_world()
        if lens_data is None:
            return None
        _, projector_origin = lens_data
        lens_centers = self._surface_camera_lens_centers_world()
        if lens_centers is None:
            return None
        telecentric_origin, _, _ = lens_centers
        return (projector_origin, telecentric_origin)

    def _ray_angle_to_y_axis_deg(self, direction: Vec3 | None) -> float | None:
        if direction is None:
            return None
        planar = vec_normalize((direction[0], direction[1], 0.0))
        if planar is None:
            return None
        y_axis: Vec3 = (0.0, 1.0, 0.0)
        dot = max(-1.0, min(1.0, vec_dot(planar, y_axis)))
        return math.degrees(math.acos(dot))

    def _projector_ray_angle_to_y_axis_deg(self) -> float | None:
        axes = self._projector_axes()
        if axes is None:
            return None
        return self._ray_angle_to_y_axis_deg(axes[3])

    def _clamp_ray_angle_to_y_axis_deg(self) -> float | None:
        telecentric_origin = self._surface_telecentric_lens_center_world()
        if telecentric_origin is None:
            return None
        return self._ray_angle_to_y_axis_deg(self._horizontal_forward_direction(telecentric_origin))

    def _update_reflected_devices(self) -> None:
        if not hasattr(self, "_device_lateral_sign"):
            self._device_lateral_sign = -1.0 if self._projection_angle_deg < 0.0 else 1.0
        if not hasattr(self, "_device_spacing_cm"):
            self._device_spacing_cm = DEFAULT_DEVICE_SPACING_CM
        center = self._base_plane_center
        half_spacing = max(0.0, self._device_spacing_cm * 0.5)
        max_half_spacing = max(0.0, self._device_distance_m)
        half_spacing = min(half_spacing, max_half_spacing)
        normal_offset = math.sqrt(
            max(0.0, self._device_distance_m * self._device_distance_m - half_spacing * half_spacing)
        )
        lateral_offset = half_spacing * self._device_lateral_sign
        if self._device_distance_m > 1e-9:
            ratio = max(-1.0, min(1.0, lateral_offset / self._device_distance_m))
            self._projection_angle_deg = math.degrees(math.asin(ratio))
        else:
            self._projection_angle_deg = 0.0
        n = self._symmetry_normal
        t = self._symmetry_tangent
        self._projector_pos = (
            center[0] + n[0] * normal_offset + t[0] * lateral_offset,
            center[1] + n[1] * normal_offset + t[1] * lateral_offset,
            center[2] + n[2] * normal_offset + t[2] * lateral_offset,
        )
        self._surface_camera_pos = (
            center[0] + n[0] * normal_offset - t[0] * lateral_offset,
            center[1] + n[1] * normal_offset - t[1] * lateral_offset,
            center[2] + n[2] * normal_offset - t[2] * lateral_offset,
        )
        for _ in range(20):
            self._align_ray_starts_to_x_axis()
            self._enforce_ray_origin_spacing()

    def _align_ray_starts_to_x_axis(self) -> None:
        for _ in range(4):
            clamp_origin = self._surface_telecentric_lens_center_world()
            if clamp_origin is not None:
                clamp_delta_y = -clamp_origin[1]
                if abs(clamp_delta_y) > 1e-6:
                    self._surface_camera_pos = (
                        self._surface_camera_pos[0],
                        self._surface_camera_pos[1] + clamp_delta_y,
                        self._surface_camera_pos[2],
                    )
            lens_data = self._projector_lens_rectangle_world()
            if lens_data is None:
                break
            _, lens_center = lens_data
            delta_y = -lens_center[1]
            if abs(delta_y) <= 1e-6:
                break
            self._projector_pos = (
                self._projector_pos[0],
                self._projector_pos[1] + delta_y,
                self._projector_pos[2],
            )

    def _enforce_ray_origin_spacing(self) -> None:
        if not hasattr(self, "_device_spacing_cm"):
            return
        origins = self._ray_origins_world()
        if origins is None:
            return
        projector_origin, clamp_origin = origins
        half_spacing = max(0.0, self._device_spacing_cm * 0.5)
        target_projector_x = half_spacing
        target_clamp_x = -half_spacing
        projector_dx = target_projector_x - projector_origin[0]
        clamp_dx = target_clamp_x - clamp_origin[0]
        if abs(projector_dx) > 1e-6:
            self._projector_pos = (
                self._projector_pos[0] + projector_dx,
                self._projector_pos[1],
                self._projector_pos[2],
            )
        if abs(clamp_dx) > 1e-6:
            self._surface_camera_pos = (
                self._surface_camera_pos[0] + clamp_dx,
                self._surface_camera_pos[1],
                self._surface_camera_pos[2],
            )

    def _compute_default_projector_fov_deg(self) -> float:
        half_h = math.atan(0.5 / PROJECTOR_THROW_RATIO)
        half_v = math.atan(math.tan(half_h) / PROJECTOR_IMAGE_ASPECT)
        return math.degrees(half_v * 2.0)

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

        self._lens_offset_x_label = QLabel(self._controls_frame)
        self._lens_offset_x_slider = QSlider(Qt.Horizontal, self._controls_frame)
        self._lens_offset_x_slider.setRange(-200, 200)
        self._lens_offset_x_slider.setValue(int(round(self.projector_lens_offset_x * 10.0)))
        self._lens_offset_x_slider.valueChanged.connect(self._on_lens_offset_x_changed)

        self._lens_offset_y_label = QLabel(self._controls_frame)
        self._lens_offset_y_slider = QSlider(Qt.Horizontal, self._controls_frame)
        self._lens_offset_y_slider.setRange(-200, 200)
        self._lens_offset_y_slider.setValue(int(round(self.projector_lens_offset_y * 10.0)))
        self._lens_offset_y_slider.valueChanged.connect(self._on_lens_offset_y_changed)

        self._record_sweep_button = QPushButton("Record surface camera sweep", self._controls_frame)
        self._record_sweep_button.setEnabled(self.projection_source == "fringe")
        self._record_sweep_button.clicked.connect(self._on_record_sweep_clicked)

        layout.addWidget(self._spacing_label)
        layout.addWidget(self._spacing_slider)
        layout.addWidget(self._distance_label)
        layout.addWidget(self._distance_slider)
        layout.addWidget(self._projector_fov_label)
        layout.addWidget(self._projector_fov_slider)
        layout.addWidget(self._lens_offset_x_label)
        layout.addWidget(self._lens_offset_x_slider)
        layout.addWidget(self._lens_offset_y_label)
        layout.addWidget(self._lens_offset_y_slider)
        layout.addWidget(self._record_sweep_button)
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
        self._lens_offset_x_label.setText(
            f"Lens offset X (right): {self.projector_lens_offset_x:.1f} cm"
        )
        self._lens_offset_y_label.setText(
            f"Lens offset Y (up): {self.projector_lens_offset_y:.1f} cm"
        )
        if hasattr(self, "_record_sweep_button"):
            self._record_sweep_button.setEnabled(
                self.mode == "plane3d"
                and self.projection_source == "fringe"
                and not self._recording_video
            )

    @Slot(int)
    def _on_spacing_changed(self, value: int) -> None:
        self._device_spacing_cm = max(0.0, float(value) / 10.0)
        self._update_reflected_devices()
        self._refresh_control_labels()
        self.update()

    @Slot(int)
    def _on_distance_changed(self, value: int) -> None:
        self.distance_m = max(0.2, float(value) / 10.0)
        self._update_reflected_devices()
        self._refresh_control_labels()
        self.update()

    @Slot(int)
    def _on_projector_fov_changed(self, value: int) -> None:
        if value <= 0:
            self.projector_fov_deg = None
        else:
            self.projector_fov_deg = float(value)
        self._refresh_control_labels()
        self.update()

    @Slot(int)
    def _on_lens_offset_x_changed(self, value: int) -> None:
        self.projector_lens_offset_x = float(value) / 10.0
        self._refresh_control_labels()
        self.update()

    @Slot(int)
    def _on_lens_offset_y_changed(self, value: int) -> None:
        self.projector_lens_offset_y = float(value) / 10.0
        self._refresh_control_labels()
        self.update()

    @Slot()
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

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save surface camera sweep video",
            "surface-camera-sweep.mp4",
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
            self.record_surface_camera_sweep_video(output_path)
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

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        if hasattr(self, "_controls_frame"):
            self._controls_frame.setGeometry(12, 12, 280, 300)
        super().resizeEvent(event)

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

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), Qt.black)

        pixmap = QPixmap.fromImage(self._processed)
        if self.mode == "plane3d":
            projector_context = self._projector_projection_context(pixmap.width(), pixmap.height())
            scene_surfaces = self._scene_surfaces()
            if self.show_ground_grid:
                self._draw_ground_grid(painter, self.width(), self.height())
            drew_projection = self._draw_plane3d_projection(
                painter,
                pixmap,
                projector_context=projector_context,
                scene_surfaces=scene_surfaces,
            )
            self._draw_projector_contours(
                painter,
                pixmap,
                self.width(),
                self.height(),
            )
            self._draw_surface_camera_minimap(
                painter,
                pixmap,
                projector_context=projector_context,
                scene_surfaces=scene_surfaces,
            )
            if drew_projection:
                return

        self._draw_scaled_fit(painter, pixmap)

    def _draw_scaled_fit(self, painter: QPainter, pixmap: QPixmap) -> None:
        mode = Qt.KeepAspectRatioByExpanding if self.fill else Qt.KeepAspectRatio
        scaled = pixmap.size().scaled(self.size(), mode)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled.width(), scaled.height(), pixmap)

    def _draw_plane3d_projection(
        self,
        painter: QPainter,
        pixmap: QPixmap,
        *,
        projector_context: tuple[Vec3, Vec3, Vec3, Vec3, float, float] | None = None,
        scene_surfaces: list[SceneSurface] | None = None,
    ) -> bool:
        return self._draw_projected_scene(
            painter,
            pixmap,
            self.width(),
            self.height(),
            projector_context=projector_context,
            scene_surfaces=scene_surfaces,
        )

    def _draw_projected_source_quad(
        self,
        painter: QPainter,
        pixmap: QPixmap,
        source_quad: QPolygonF,
        destination_quad: QPolygonF,
        *,
        clip_quad: QPolygonF | None = None,
    ) -> None:
        transform = QTransform.quadToQuad(source_quad, destination_quad)
        if not isinstance(transform, QTransform):
            return

        painter.save()
        clip_path = QPainterPath()
        clip_path.addPolygon(clip_quad if clip_quad is not None else destination_quad)
        painter.setClipPath(clip_path)
        painter.setTransform(transform, True)
        painter.drawPixmap(0, 0, pixmap)
        painter.restore()

    def _draw_solid_quad(
        self,
        painter: QPainter,
        destination_quad: QPolygonF,
        color: QColor,
    ) -> None:
        painter.save()
        painter.setPen(QPen(QColor(120, 130, 150), 1))
        painter.setBrush(color)
        painter.drawPolygon(destination_quad)
        painter.restore()

    def _draw_field_object_3d(
        self,
        painter: QPainter,
        viewport_width: int,
        viewport_height: int,
        *,
        context: CameraContext | None = None,
    ) -> bool:
        if self.field_width_m <= 0 or self.field_height_m <= 0:
            return False
        if context is None:
            context = self._camera_projection_context(viewport_width, viewport_height)
        if context is None:
            return False

        face_polygons: list[tuple[float, QPolygonF]] = []
        for face_world in self._field_object_faces():
            projected_face: list[QPointF] = []
            for point in face_world:
                projected = self._project_world_point(point, context)
                if projected is None:
                    projected_face = []
                    break
                projected_face.append(projected)
            if len(projected_face) != 4:
                continue
            avg_depth = sum(self._world_to_camera(p, context)[2] for p in face_world) / 4.0
            face_polygons.append((avg_depth, QPolygonF(projected_face)))

        if not face_polygons:
            return False

        face_polygons.sort(key=lambda item: item[0], reverse=True)
        painter.save()
        painter.setPen(QPen(QColor(95, 132, 170), 1.2))
        painter.setBrush(QColor(70, 96, 124, 140))
        for _, polygon in face_polygons:
            painter.drawPolygon(polygon)
        painter.restore()
        return True

    def _field_object_world_corners(self) -> list[Vec3]:
        frame = self._field_object_frame()
        if frame is None:
            return []
        plane_center, right, up, normal = frame
        half_w = self.field_width_m * 0.5
        half_h = self.field_height_m * 0.5
        depth = self._field_object_depth()
        gap = FIELD_OBJECT_PLANE_GAP_M
        back_center = (
            plane_center[0] + normal[0] * gap,
            plane_center[1] + normal[1] * gap,
            plane_center[2] + normal[2] * gap,
        )
        front_center = (
            plane_center[0] + normal[0] * (gap + depth),
            plane_center[1] + normal[1] * (gap + depth),
            plane_center[2] + normal[2] * (gap + depth),
        )

        def rect(center: Vec3) -> list[Vec3]:
            return [
                (
                    center[0] - right[0] * half_w + up[0] * half_h,
                    center[1] - right[1] * half_w + up[1] * half_h,
                    center[2] - right[2] * half_w + up[2] * half_h,
                ),
                (
                    center[0] + right[0] * half_w + up[0] * half_h,
                    center[1] + right[1] * half_w + up[1] * half_h,
                    center[2] + right[2] * half_w + up[2] * half_h,
                ),
                (
                    center[0] + right[0] * half_w - up[0] * half_h,
                    center[1] + right[1] * half_w - up[1] * half_h,
                    center[2] + right[2] * half_w - up[2] * half_h,
                ),
                (
                    center[0] - right[0] * half_w - up[0] * half_h,
                    center[1] - right[1] * half_w - up[1] * half_h,
                    center[2] - right[2] * half_w - up[2] * half_h,
                ),
            ]

        return [*rect(front_center), *rect(back_center)]

    def _field_object_faces(self) -> list[list[Vec3]]:
        world_corners = self._field_object_world_corners()
        if len(world_corners) != 8:
            return []
        face_indices = [
            (0, 1, 2, 3),
            (4, 5, 6, 7),
            (0, 1, 5, 4),
            (1, 2, 6, 5),
            (2, 3, 7, 6),
            (3, 0, 4, 7),
        ]
        return [[world_corners[i] for i in face] for face in face_indices]

    def _field_object_depth(self) -> float:
        return max(0.25, min(self.field_width_m, self.field_height_m) * 0.6)

    def _field_object_frame(self) -> tuple[Vec3, Vec3, Vec3, Vec3] | None:
        plane_center = self._plane_center()
        corners = self._surface_world_corners(
            plane_center,
            self.plane_width_m,
            self.plane_height_m,
        )
        right = vec_normalize(vec_subtract(corners[1], corners[0]))
        up = vec_normalize(vec_subtract(corners[0], corners[3]))
        if right is None or up is None:
            return None
        normal = vec_normalize(vec_cross(right, up))
        if normal is None:
            return None
        if vec_dot(normal, self._symmetry_normal) < 0.0:
            normal = (-normal[0], -normal[1], -normal[2])
        return (plane_center, right, up, normal)

    def _scene_surfaces(self) -> list[SceneSurface]:
        surfaces: list[SceneSurface] = []
        if self.project_projection_plane:
            surfaces.append(
                (
                    "Projection Plane",
                    self._surface_world_corners(
                        self._plane_center(),
                        self.plane_width_m,
                        self.plane_height_m,
                    ),
                    QColor(56, 64, 82),
                )
            )
        if self.project_field_object:
            for index, face in enumerate(self._field_object_faces()):
                surfaces.append((f"Field Object {index + 1}", face, QColor(70, 96, 124)))
        return surfaces

    def _ray_surface_intersection(
        self,
        ray_origin: Vec3,
        ray_direction: Vec3,
        surface: list[Vec3],
    ) -> tuple[float, Vec3] | None:
        if len(surface) < 3:
            return None
        edge_u = vec_subtract(surface[1], surface[0])
        edge_v = vec_subtract(surface[-1], surface[0])
        normal = vec_normalize(vec_cross(edge_u, edge_v))
        if normal is None:
            return None

        denominator = vec_dot(ray_direction, normal)
        if abs(denominator) <= 1e-8:
            return None
        ray_to_plane = vec_subtract(surface[0], ray_origin)
        distance = vec_dot(ray_to_plane, normal) / denominator
        if distance <= 1e-5:
            return None

        hit = (
            ray_origin[0] + ray_direction[0] * distance,
            ray_origin[1] + ray_direction[1] * distance,
            ray_origin[2] + ray_direction[2] * distance,
        )
        edge_signs: list[float] = []
        for index, corner in enumerate(surface):
            next_corner = surface[(index + 1) % len(surface)]
            edge = vec_subtract(next_corner, corner)
            to_hit = vec_subtract(hit, corner)
            edge_signs.append(vec_dot(vec_cross(edge, to_hit), normal))
        if not (
            all(sign >= -1e-6 for sign in edge_signs)
            or all(sign <= 1e-6 for sign in edge_signs)
        ):
            return None
        return (distance, hit)

    def _first_projector_hit(
        self,
        x_pixel: float,
        y_pixel: float,
        image_width: int,
        image_height: int,
        projector_context: tuple[Vec3, Vec3, Vec3, Vec3, float, float],
        surfaces: list[SceneSurface],
    ) -> tuple[int, Vec3] | None:
        ray_direction = self._projector_ray_direction(
            x_pixel,
            y_pixel,
            image_width,
            image_height,
            projector_context,
        )
        if ray_direction is None:
            return None

        projector_origin = projector_context[0]
        nearest: tuple[float, int, Vec3] | None = None
        for surface_index, (_, corners, _) in enumerate(surfaces):
            intersection = self._ray_surface_intersection(
                projector_origin,
                ray_direction,
                corners,
            )
            if intersection is None:
                continue
            distance, hit = intersection
            if nearest is None or distance < nearest[0]:
                nearest = (distance, surface_index, hit)
        if nearest is None:
            return None
        return (nearest[1], nearest[2])

    def _first_telecentric_scan_hit(
        self,
        x_pixel: float,
        y_pixel: float,
        image_width: int,
        image_height: int,
        scan_context: TelecentricScanContext,
        surfaces: list[SceneSurface],
    ) -> tuple[int, Vec3] | None:
        if image_width <= 0 or image_height <= 0:
            return None
        origin, right, up, forward, half_w, half_h = scan_context
        nx = (2.0 * x_pixel / float(image_width)) - 1.0
        ny = 1.0 - (2.0 * y_pixel / float(image_height))
        ray_origin = (
            origin[0] + right[0] * (nx * half_w) + up[0] * (ny * half_h),
            origin[1] + right[1] * (nx * half_w) + up[1] * (ny * half_h),
            origin[2] + right[2] * (nx * half_w) + up[2] * (ny * half_h),
        )
        nearest: tuple[float, int, Vec3] | None = None
        for surface_index, (_, corners, _) in enumerate(surfaces):
            intersection = self._ray_surface_intersection(ray_origin, forward, corners)
            if intersection is None:
                continue
            distance, hit = intersection
            if nearest is None or distance < nearest[0]:
                nearest = (distance, surface_index, hit)
        if nearest is None:
            return None
        return (nearest[1], nearest[2])

    def _telecentric_ray_origin(
        self,
        x_pixel: float,
        y_pixel: float,
        image_width: int,
        image_height: int,
        scan_context: TelecentricScanContext,
    ) -> Vec3 | None:
        if image_width <= 0 or image_height <= 0:
            return None
        origin, right, up, _, half_w, half_h = scan_context
        nx = (2.0 * x_pixel / float(image_width)) - 1.0
        ny = 1.0 - (2.0 * y_pixel / float(image_height))
        return (
            origin[0] + right[0] * (nx * half_w) + up[0] * (ny * half_h),
            origin[1] + right[1] * (nx * half_w) + up[1] * (ny * half_h),
            origin[2] + right[2] * (nx * half_w) + up[2] * (ny * half_h),
        )

    def _primary_surface_fringe_context(
        self,
        image_width: int,
        image_height: int,
        scan_context: TelecentricScanContext | None,
    ) -> FringeRectContext | None:
        primary_surface = self._primary_projection_surface()
        if primary_surface is None or scan_context is None:
            return None
        surface_center, surface_width, surface_height = primary_surface
        surface_corners = self._surface_world_corners(
            surface_center,
            surface_width,
            surface_height,
        )
        if len(surface_corners) != 4:
            return None
        origin = surface_corners[3]
        right = vec_normalize(vec_subtract(surface_corners[2], surface_corners[3]))
        up = vec_normalize(vec_subtract(surface_corners[0], surface_corners[3]))
        if right is None or up is None:
            return None
        normal = vec_normalize(vec_cross(right, up))
        if normal is None:
            return None

        corner_samples = [
            (0.0, 0.0),
            (float(image_width), 0.0),
            (float(image_width), float(image_height)),
            (0.0, float(image_height)),
        ]
        u_values: list[float] = []
        v_values: list[float] = []
        forward = scan_context[3]
        for sx, sy in corner_samples:
            ray_origin = self._telecentric_ray_origin(
                sx,
                sy,
                image_width,
                image_height,
                scan_context,
            )
            if ray_origin is None:
                return None
            hit = self._intersect_ray_with_plane(
                ray_origin,
                forward,
                origin,
                normal,
            )
            if hit is None:
                return None
            rel = vec_subtract(hit, origin)
            u_values.append(vec_dot(rel, right))
            v_values.append(vec_dot(rel, up))

        return (
            origin,
            normal,
            right,
            up,
            min(u_values),
            max(u_values),
            min(v_values),
            max(v_values),
        )

    def _projector_hit_on_fringe_plane(
        self,
        x_pixel: float,
        y_pixel: float,
        image_width: int,
        image_height: int,
        projector_context: tuple[Vec3, Vec3, Vec3, Vec3, float, float],
        fringe_context: FringeRectContext | None,
    ) -> Vec3 | None:
        if fringe_context is None:
            return None
        ray_direction = self._projector_ray_direction(
            x_pixel,
            y_pixel,
            image_width,
            image_height,
            projector_context,
        )
        if ray_direction is None:
            return None
        plane_origin, plane_normal, _, _, _, _, _, _ = fringe_context
        return self._intersect_ray_with_plane(
            projector_context[0],
            ray_direction,
            plane_origin,
            plane_normal,
        )

    def _draw_projected_scene(
        self,
        painter: QPainter,
        pixmap: QPixmap,
        viewport_width: int,
        viewport_height: int,
        *,
        view_context: CameraContext | None = None,
        columns: int = PROJECTOR_RAYCAST_COLUMNS,
        rows: int = PROJECTOR_RAYCAST_ROWS,
        edge_subdivisions: int = PROJECTOR_RAYCAST_EDGE_SUBDIVISIONS,
        projector_context: tuple[Vec3, Vec3, Vec3, Vec3, float, float] | None = None,
        scene_surfaces: list[SceneSurface] | None = None,
    ) -> bool:
        if pixmap.width() <= 0 or pixmap.height() <= 0:
            return False
        if view_context is None:
            view_context = self._camera_projection_context(viewport_width, viewport_height)
        if view_context is None:
            return False
        if projector_context is None:
            projector_context = self._projector_projection_context(pixmap.width(), pixmap.height())
        if projector_context is None:
            return False

        surfaces = scene_surfaces if scene_surfaces is not None else self._scene_surfaces()
        if not surfaces:
            return False

        telecentric_scan_context = self._surface_camera_telecentric_scan_context(
            pixmap.width(),
            pixmap.height(),
        )
        fringe_rect_context = (
            self._primary_surface_fringe_context(
                pixmap.width(),
                pixmap.height(),
                telecentric_scan_context,
            )
            if self.projection_source == "fringe"
            else None
        )
        surface_cells: list[list[tuple[QPolygonF, QPolygonF]]] = [
            [] for _ in surfaces
        ]
        columns = max(2, columns)
        rows = max(2, rows)
        edge_subdivisions = max(0, edge_subdivisions)
        for row in range(rows):
            y0 = pixmap.height() * row / rows
            y1 = pixmap.height() * (row + 1) / rows
            for column in range(columns):
                x0 = pixmap.width() * column / columns
                x1 = pixmap.width() * (column + 1) / columns
                self._add_projected_cell(
                    surface_cells,
                    surfaces,
                    pixmap,
                    view_context,
                    projector_context,
                    telecentric_scan_context,
                    fringe_rect_context,
                    x0,
                    y0,
                    x1,
                    y1,
                    edge_subdivisions,
                )

        surface_order: list[tuple[float, int, QPolygonF]] = []
        for index, (_, corners, _) in enumerate(surfaces):
            projected_surface: list[QPointF] = []
            for corner in corners:
                projected = self._project_world_point(corner, view_context)
                if projected is None:
                    projected_surface = []
                    break
                projected_surface.append(projected)
            if len(projected_surface) != len(corners):
                continue
            avg_depth = sum(self._world_to_camera(corner, view_context)[2] for corner in corners) / len(corners)
            surface_order.append((avg_depth, index, QPolygonF(projected_surface)))

        if not surface_order:
            return False
        surface_order.sort(key=lambda item: item[0], reverse=True)
        for _, surface_index, projected_surface in surface_order:
            _, _, color = surfaces[surface_index]
            self._draw_solid_quad(painter, projected_surface, color)
            for source_quad, destination_quad in surface_cells[surface_index]:
                self._draw_projected_source_quad(
                    painter,
                    pixmap,
                    source_quad,
                    destination_quad,
                    clip_quad=projected_surface,
                )
        return True

    def _add_projected_cell(
        self,
        surface_cells: list[list[tuple[QPolygonF, QPolygonF]]],
        surfaces: list[SceneSurface],
        pixmap: QPixmap,
        view_context: CameraContext,
        projector_context: tuple[Vec3, Vec3, Vec3, Vec3, float, float],
        scan_mask_context: TelecentricScanContext | None,
        fringe_rect_context: FringeRectContext | None,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        remaining_subdivisions: int,
    ) -> None:
        sample_points = [
            ((x0 + x1) * 0.5, (y0 + y1) * 0.5),
            (x0, y0),
            ((x0 + x1) * 0.5, y0),
            (x1, y0),
            (x1, (y0 + y1) * 0.5),
            (x1, y1),
            ((x0 + x1) * 0.5, y1),
            (x0, y1),
            (x0, (y0 + y1) * 0.5),
        ]
        sample_hits: list[tuple[int, bool]] = []
        for sx, sy in sample_points:
            hit = self._first_projector_hit(
                sx,
                sy,
                pixmap.width(),
                pixmap.height(),
                projector_context,
                surfaces,
            )
            if hit is not None:
                mask_point = hit[1]
                inside_mask = self._world_point_inside_projection_context(
                    mask_point,
                    scan_mask_context,
                )
                if fringe_rect_context is not None:
                    plane_hit = self._projector_hit_on_fringe_plane(
                        sx,
                        sy,
                        pixmap.width(),
                        pixmap.height(),
                        projector_context,
                        fringe_rect_context,
                    )
                    if plane_hit is None:
                        continue
                    mask_point = plane_hit
                    inside_mask = self._world_point_inside_fringe_rect(
                        mask_point,
                        fringe_rect_context,
                    )
                sample_hits.append(
                    (
                        hit[0],
                        inside_mask,
                    )
                )

        if not sample_hits:
            return
        center_surface_index, center_inside_mask = sample_hits[0]
        if (
            remaining_subdivisions > 0
            and any(
                surface_index != center_surface_index or inside_mask != center_inside_mask
                for surface_index, inside_mask in sample_hits[1:]
            )
        ):
            xm = (x0 + x1) * 0.5
            ym = (y0 + y1) * 0.5
            next_depth = remaining_subdivisions - 1
            self._add_projected_cell(
                surface_cells,
                surfaces,
                pixmap,
                view_context,
                projector_context,
                scan_mask_context,
                fringe_rect_context,
                x0,
                y0,
                xm,
                ym,
                next_depth,
            )
            self._add_projected_cell(
                surface_cells,
                surfaces,
                pixmap,
                view_context,
                projector_context,
                scan_mask_context,
                fringe_rect_context,
                xm,
                y0,
                x1,
                ym,
                next_depth,
            )
            self._add_projected_cell(
                surface_cells,
                surfaces,
                pixmap,
                view_context,
                projector_context,
                scan_mask_context,
                fringe_rect_context,
                xm,
                ym,
                x1,
                y1,
                next_depth,
            )
            self._add_projected_cell(
                surface_cells,
                surfaces,
                pixmap,
                view_context,
                projector_context,
                scan_mask_context,
                fringe_rect_context,
                x0,
                ym,
                xm,
                y1,
                next_depth,
            )
            return
        if not center_inside_mask:
            return

        source_points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        surface_corners = surfaces[center_surface_index][1]
        edge_u = vec_subtract(surface_corners[1], surface_corners[0])
        edge_v = vec_subtract(surface_corners[-1], surface_corners[0])
        surface_normal = vec_normalize(vec_cross(edge_u, edge_v))
        if surface_normal is None:
            return

        hit_points: list[Vec3] = []
        for sx, sy in source_points:
            ray_direction = self._projector_ray_direction(
                sx,
                sy,
                pixmap.width(),
                pixmap.height(),
                projector_context,
            )
            if ray_direction is None:
                return
            hit = self._intersect_ray_with_plane(
                projector_context[0],
                ray_direction,
                surface_corners[0],
                surface_normal,
            )
            if hit is None:
                return
            hit_points.append(hit)

        destination_points = [
            self._project_world_point(hit, view_context)
            for hit in hit_points
        ]
        if any(point is None for point in destination_points):
            return

        if fringe_rect_context is not None:
            source_quad_points: list[QPointF] = []
            for sx, sy in source_points:
                plane_hit = self._projector_hit_on_fringe_plane(
                    sx,
                    sy,
                    pixmap.width(),
                    pixmap.height(),
                    projector_context,
                    fringe_rect_context,
                )
                if plane_hit is None:
                    return
                source_point = self._fringe_source_point_for_world(
                    plane_hit,
                    fringe_rect_context,
                    pixmap.width(),
                    pixmap.height(),
                )
                if source_point is None:
                    return
                source_quad_points.append(source_point)
            source_quad = QPolygonF(source_quad_points)
        else:
            source_quad = QPolygonF([QPointF(sx, sy) for sx, sy in source_points])
        destination_quad = QPolygonF([point for point in destination_points if point is not None])
        surface_cells[center_surface_index].append((source_quad, destination_quad))

    def _world_point_inside_projection_context(
        self,
        point: Vec3,
        context: TelecentricScanContext | None,
    ) -> bool:
        if context is None:
            return True
        origin, right, up, forward, half_w, half_h = context
        rel = vec_subtract(point, origin)
        depth = vec_dot(rel, forward)
        if depth <= 1e-5:
            return False
        if half_w <= 1e-9 or half_h <= 1e-9:
            return False
        lateral_x = vec_dot(rel, right)
        lateral_y = vec_dot(rel, up)
        return abs(lateral_x) <= half_w + 1e-5 and abs(lateral_y) <= half_h + 1e-5

    def _world_point_inside_fringe_rect(
        self,
        point: Vec3,
        context: FringeRectContext | None,
    ) -> bool:
        if context is None:
            return True
        origin, _, right, up, u_min, u_max, v_min, v_max = context
        rel = vec_subtract(point, origin)
        u = vec_dot(rel, right)
        v = vec_dot(rel, up)
        return (
            u_min - 1e-5 <= u <= u_max + 1e-5
            and v_min - 1e-5 <= v <= v_max + 1e-5
        )

    def _fringe_source_point_for_world(
        self,
        point: Vec3,
        context: FringeRectContext,
        image_width: int,
        image_height: int,
    ) -> QPointF | None:
        origin, _, right, up, u_min, u_max, v_min, v_max = context
        span_u = u_max - u_min
        span_v = v_max - v_min
        if span_u <= 1e-6 or span_v <= 1e-6:
            return None
        rel = vec_subtract(point, origin)
        u = vec_dot(rel, right)
        v = vec_dot(rel, up)
        if not self._world_point_inside_fringe_rect(point, context):
            return None
        nx = (u - u_min) / span_u
        ny = 1.0 - ((v - v_min) / span_v)
        x = nx * float(image_width)
        y = ny * float(image_height)
        return QPointF(x, y)

    def _surface_corners(
        self, center: Vec3, width: float, height: float
    ) -> list[Vec3]:
        half_w = width / 2.0
        half_h = height / 2.0
        if self.projector_axis == "y":
            return [
                (center[0] - half_w, center[1], center[2] + half_h),
                (center[0] + half_w, center[1], center[2] + half_h),
                (center[0] + half_w, center[1], center[2] - half_h),
                (center[0] - half_w, center[1], center[2] - half_h),
            ]
        return [
            (center[0] - half_w, center[1] + half_h, center[2]),
            (center[0] + half_w, center[1] + half_h, center[2]),
            (center[0] + half_w, center[1] - half_h, center[2]),
            (center[0] - half_w, center[1] - half_h, center[2]),
        ]

    def _surface_world_corners(
        self, center: Vec3, width: float, height: float
    ) -> list[Vec3]:
        return [
            self._rotate_plane_point(corner, center)
            for corner in self._surface_corners(center, width, height)
        ]

    def _projector_projection_context(
        self, image_width: int, image_height: int
    ) -> tuple[Vec3, Vec3, Vec3, Vec3, float, float] | None:
        if image_width <= 0 or image_height <= 0:
            return None
        axes = self._projector_axes()
        if axes is None:
            return None
        origin, right, up, forward = axes
        aspect = float(image_width) / float(image_height)
        effective_fov_deg = self._effective_projector_fov_deg()
        tan_half_fov = math.tan(math.radians(effective_fov_deg) / 2.0)
        return (origin, right, up, forward, tan_half_fov, aspect)

    def _lens_plane_corners(
        self,
        center: Vec3,
        right: Vec3,
        up: Vec3,
        width: float,
        height: float,
    ) -> list[Vec3]:
        half_w = width * 0.5
        half_h = height * 0.5
        return [
            (
                center[0] - right[0] * half_w + up[0] * half_h,
                center[1] - right[1] * half_w + up[1] * half_h,
                center[2] - right[2] * half_w + up[2] * half_h,
            ),
            (
                center[0] + right[0] * half_w + up[0] * half_h,
                center[1] + right[1] * half_w + up[1] * half_h,
                center[2] + right[2] * half_w + up[2] * half_h,
            ),
            (
                center[0] + right[0] * half_w - up[0] * half_h,
                center[1] + right[1] * half_w - up[1] * half_h,
                center[2] + right[2] * half_w - up[2] * half_h,
            ),
            (
                center[0] - right[0] * half_w - up[0] * half_h,
                center[1] - right[1] * half_w - up[1] * half_h,
                center[2] - right[2] * half_w - up[2] * half_h,
            ),
        ]

    def _projector_horizontal_target(self, origin: Vec3) -> Vec3:
        target = self._look_target()
        primary_surface = self._primary_projection_surface()
        if primary_surface is not None:
            target = primary_surface[0]
        return (target[0], target[1], origin[2])

    def _horizontal_forward_direction(self, origin: Vec3) -> Vec3:
        target = self._projector_horizontal_target(origin)
        direction = vec_normalize((target[0] - origin[0], target[1] - origin[1], 0.0))
        if direction is not None:
            return direction
        tangent = vec_normalize((self._symmetry_tangent[0], self._symmetry_tangent[1], 0.0))
        if tangent is not None:
            return tangent
        return (0.0, 1.0, 0.0)

    def _projector_chassis_axes(self) -> tuple[Vec3, Vec3, Vec3, Vec3] | None:
        chassis_origin = self._projector_pos
        forward = self._horizontal_forward_direction(chassis_origin)
        world_up: Vec3 = (0.0, 0.0, 1.0)
        if abs(vec_dot(forward, world_up)) > 0.98:
            world_up = (0.0, 1.0, 0.0)
        right = vec_normalize(vec_cross(forward, world_up))
        if right is None:
            return None
        up = vec_cross(right, forward)
        return (chassis_origin, right, up, forward)

    def _projector_lens_rectangle_world(self) -> tuple[list[Vec3], Vec3] | None:
        chassis_axes = self._projector_chassis_axes()
        if chassis_axes is None:
            return None
        chassis_origin, right, up, forward = chassis_axes

        lens_half_w = PROJECTOR_LENS_WINDOW_WIDTH_CM * 0.5
        lens_half_h = PROJECTOR_LENS_WINDOW_HEIGHT_CM * 0.5
        cx = self.projector_lens_offset_x
        cy = self.projector_lens_offset_y
        cz = self.projector_lens_offset_z + PROJECTOR_LENS_FACE_EPS

        def local_to_world(lx: float, ly: float, lz: float) -> Vec3:
            return (
                chassis_origin[0] + right[0] * lx + up[0] * ly + forward[0] * lz,
                chassis_origin[1] + right[1] * lx + up[1] * ly + forward[1] * lz,
                chassis_origin[2] + right[2] * lx + up[2] * ly + forward[2] * lz,
            )

        center = local_to_world(cx, cy, cz)
        corners: list[Vec3] = [
            local_to_world(cx - lens_half_w, cy + lens_half_h, cz),
            local_to_world(cx + lens_half_w, cy + lens_half_h, cz),
            local_to_world(cx + lens_half_w, cy - lens_half_h, cz),
            local_to_world(cx - lens_half_w, cy - lens_half_h, cz),
        ]
        return (corners, center)

    def _projector_axes(self) -> tuple[Vec3, Vec3, Vec3, Vec3] | None:
        lens_data = self._projector_lens_rectangle_world()
        if lens_data is None:
            return None
        _, lens_origin = lens_data
        lens_forward = self._horizontal_forward_direction(lens_origin)
        world_up: Vec3 = (0.0, 0.0, 1.0)
        if abs(vec_dot(lens_forward, world_up)) > 0.98:
            world_up = (0.0, 1.0, 0.0)
        lens_right = vec_normalize(vec_cross(lens_forward, world_up))
        if lens_right is None:
            return None
        lens_up = vec_cross(lens_right, lens_forward)
        return (lens_origin, lens_right, lens_up, lens_forward)

    def _effective_projector_fov_now(self) -> float:
        return self._effective_projector_fov_deg()

    def _effective_projector_fov_deg(self) -> float:
        if self.projector_fov_deg is not None:
            return max(1.1, min(179.0, self.projector_fov_deg))
        return self._default_projector_fov_deg

    def _projector_ray_direction(
        self,
        x_pixel: float,
        y_pixel: float,
        image_width: int,
        image_height: int,
        projector_context: tuple[Vec3, Vec3, Vec3, Vec3, float, float],
    ) -> Vec3 | None:
        origin, right, up, forward, tan_half_fov, aspect = projector_context
        nx = (2.0 * x_pixel / float(image_width)) - 1.0
        ny = 1.0 - (2.0 * y_pixel / float(image_height))
        direction = (
            forward[0] + right[0] * (nx * aspect * tan_half_fov) + up[0] * (ny * tan_half_fov),
            forward[1] + right[1] * (nx * aspect * tan_half_fov) + up[1] * (ny * tan_half_fov),
            forward[2] + right[2] * (nx * aspect * tan_half_fov) + up[2] * (ny * tan_half_fov),
        )
        return vec_normalize(direction)

    def _intersect_ray_with_plane(
        self,
        ray_origin: Vec3,
        ray_direction: Vec3,
        plane_point: Vec3,
        plane_normal: Vec3,
    ) -> Vec3 | None:
        denominator = vec_dot(ray_direction, plane_normal)
        if abs(denominator) <= 1e-8:
            return None
        ray_to_plane = vec_subtract(plane_point, ray_origin)
        t = vec_dot(ray_to_plane, plane_normal) / denominator
        if t <= 1e-5:
            return None
        return (
            ray_origin[0] + ray_direction[0] * t,
            ray_origin[1] + ray_direction[1] * t,
            ray_origin[2] + ray_direction[2] * t,
        )

    def _draw_projector_contours(
        self,
        painter: QPainter,
        pixmap: QPixmap,
        viewport_width: int,
        viewport_height: int,
    ) -> None:
        self._projector_projection_hit_world = None
        self._projector_ray_origin_world = None
        self._clamp_projection_hit_world = None
        self._clamp_ray_origin_world = None
        self._surface_camera_lens_origin_world = None
        view_context = self._camera_projection_context(viewport_width, viewport_height)
        if view_context is None:
            return
        if pixmap.width() <= 0 or pixmap.height() <= 0:
            return

        contour_pen = QPen(QColor(255, 235, 110, 190), 1)
        painter.setPen(contour_pen)
        projector_axes = self._projector_axes()
        if projector_axes is None:
            return
        projector_context = self._projector_projection_context(pixmap.width(), pixmap.height())
        if projector_context is None:
            return
        lens_data = self._projector_lens_rectangle_world()
        if lens_data is None:
            return
        lens_corners_world, lens_center_world = lens_data
        self._projector_ray_origin_world = lens_center_world

        for i in range(len(lens_corners_world)):
            segment = self._project_segment_clipped(
                lens_corners_world[i],
                lens_corners_world[(i + 1) % len(lens_corners_world)],
                view_context,
            )
            if segment is None:
                continue
            pa, pb = segment
            painter.drawLine(pa, pb)

        scene_surfaces = self._scene_surfaces()
        if not scene_surfaces:
            return

        source_corners = [
            (0.0, 0.0),
            (float(pixmap.width()), 0.0),
            (float(pixmap.width()), float(pixmap.height())),
            (0.0, float(pixmap.height())),
        ]
        hit_world_points: list[Vec3] = []
        projection_points: list[QPointF] = []
        for sx, sy in source_corners:
            hit = self._first_projector_hit(
                sx,
                sy,
                pixmap.width(),
                pixmap.height(),
                projector_context,
                scene_surfaces,
            )
            if hit is None:
                continue
            hit_world = hit[1]
            projected = self._project_world_point(hit_world, view_context)
            if projected is None:
                continue
            hit_world_points.append(hit_world)
            projection_points.append(projected)

        if len(projection_points) == 4:
            projection_quad = QPolygonF(projection_points)
            painter.save()
            raw_pen = QPen(QColor(255, 235, 110, 120), 1)
            raw_pen.setStyle(Qt.DashLine)
            painter.setPen(raw_pen)
            for i in range(projection_quad.count()):
                pa = projection_quad.at(i)
                pb = projection_quad.at((i + 1) % projection_quad.count())
                painter.drawLine(pa, pb)
            painter.setPen(QColor(255, 235, 110, 150))
            painter.drawText(projection_quad.at(0) + QPointF(6.0, -6.0), "Raw projector frustum")
            painter.restore()
        for i, hit in enumerate(hit_world_points):
            lens_corner = lens_corners_world[i % len(lens_corners_world)]
            segment = self._project_segment_clipped(lens_corner, hit, view_context)
            if segment is None:
                continue
            pa, pb = segment
            painter.drawLine(pa, pb)

        center_hit = self._first_projector_hit(
            pixmap.width() * 0.5,
            pixmap.height() * 0.5,
            pixmap.width(),
            pixmap.height(),
            projector_context,
            scene_surfaces,
        )
        projector_hit = center_hit[1] if center_hit is not None else None
        if projector_hit is not None:
            center_line = self._project_segment_clipped(
                lens_center_world, projector_hit, view_context
            )
            if center_line is not None:
                painter.save()
                painter.setPen(QPen(QColor(255, 190, 90, 210), 1.5))
                pa, pb = center_line
                painter.drawLine(pa, pb)
                painter.restore()
        self._projector_projection_hit_world = projector_hit

        clamp_context = self._surface_camera_telecentric_scan_context(
            pixmap.width(),
            pixmap.height(),
        )
        if clamp_context is not None:
            lens_centers = self._surface_camera_lens_centers_world()
            if lens_centers is None:
                return
            clamp_origin, camera_lens_origin, _ = lens_centers
            self._clamp_ray_origin_world = clamp_origin
            self._surface_camera_lens_origin_world = camera_lens_origin
            clamp_right = clamp_context[1]
            clamp_up = clamp_context[2]
            clamp_corners_world = self._lens_plane_corners(
                clamp_origin,
                clamp_right,
                clamp_up,
                TELECENTRIC_LENS_DIAMETER_CM,
                TELECENTRIC_LENS_DIAMETER_CM,
            )
            camera_lens_corners_world = self._lens_plane_corners(
                camera_lens_origin,
                clamp_right,
                clamp_up,
                SURFACE_CAMERA_REAR_LENS_DIAMETER_CM,
                SURFACE_CAMERA_REAR_LENS_DIAMETER_CM,
            )
            painter.save()
            painter.setPen(QPen(QColor(92, 222, 255, 230), 1.4))
            for corners in (clamp_corners_world, camera_lens_corners_world):
                for i in range(len(corners)):
                    segment = self._project_segment_clipped(
                        corners[i],
                        corners[(i + 1) % len(corners)],
                        view_context,
                    )
                    if segment is None:
                        continue
                    pa, pb = segment
                    painter.drawLine(pa, pb)
            painter.setPen(QPen(QColor(115, 235, 255, 150), 1))
            for telecentric_corner, camera_corner in zip(
                clamp_corners_world,
                camera_lens_corners_world,
            ):
                segment = self._project_segment_clipped(
                    telecentric_corner,
                    camera_corner,
                    view_context,
                )
                if segment is None:
                    continue
                pa, pb = segment
                painter.drawLine(pa, pb)
            axis_segment = self._project_segment_clipped(
                camera_lens_origin,
                clamp_origin,
                view_context,
            )
            if axis_segment is not None:
                painter.setPen(QPen(QColor(155, 245, 255, 190), 1.4))
                pa, pb = axis_segment
                painter.drawLine(pa, pb)
            painter.restore()

            clamp_projection_points: list[QPointF] = []
            clamp_hit_world_points: list[Vec3] = []
            for sx, sy in source_corners:
                clamp_hit = self._first_telecentric_scan_hit(
                    sx,
                    sy,
                    pixmap.width(),
                    pixmap.height(),
                    clamp_context,
                    scene_surfaces,
                )
                if clamp_hit is None:
                    continue
                hit_world = clamp_hit[1]
                projected = self._project_world_point(hit_world, view_context)
                if projected is None:
                    continue
                clamp_hit_world_points.append(hit_world)
                clamp_projection_points.append(projected)

            if len(clamp_projection_points) == 4:
                clamp_quad = QPolygonF(clamp_projection_points)
                painter.save()
                fill_color = QColor(92, 222, 255, 48)
                painter.setBrush(fill_color)
                painter.setPen(QPen(QColor(92, 222, 255, 220), 1.6))
                painter.drawPolygon(clamp_quad)
                painter.setBrush(Qt.NoBrush)
                for i in range(clamp_quad.count()):
                    pa = clamp_quad.at(i)
                    pb = clamp_quad.at((i + 1) % clamp_quad.count())
                    painter.drawLine(pa, pb)
                painter.restore()

            for i, hit in enumerate(clamp_hit_world_points):
                clamp_corner = clamp_corners_world[i % len(clamp_corners_world)]
                segment = self._project_segment_clipped(clamp_corner, hit, view_context)
                if segment is None:
                    continue
                painter.save()
                painter.setPen(QPen(QColor(92, 222, 255, 160), 1))
                pa, pb = segment
                painter.drawLine(pa, pb)
                painter.restore()

            clamp_center_hit = self._first_telecentric_scan_hit(
                pixmap.width() * 0.5,
                pixmap.height() * 0.5,
                pixmap.width(),
                pixmap.height(),
                clamp_context,
                scene_surfaces,
            )
            clamp_hit = clamp_center_hit[1] if clamp_center_hit is not None else None
            self._clamp_projection_hit_world = clamp_hit
            if clamp_hit is not None:
                clamp_segment = self._project_segment_clipped(clamp_origin, clamp_hit, view_context)
                if clamp_segment is not None:
                    painter.save()
                    painter.setPen(QPen(QColor(92, 222, 255, 210), 1.5))
                    pa, pb = clamp_segment
                    painter.drawLine(pa, pb)
                    painter.restore()

        clamp_hit = self._clamp_projection_hit_world

        projector_hit_2d = (
            self._project_world_point(projector_hit, view_context)
            if projector_hit is not None
            else None
        )
        clamp_hit_2d = (
            self._project_world_point(clamp_hit, view_context)
            if clamp_hit is not None
            else None
        )
        projector_origin = getattr(self, "_projector_ray_origin_world", None)
        clamp_origin = self._clamp_ray_origin_world
        camera_lens_origin = getattr(self, "_surface_camera_lens_origin_world", None)
        projector_origin_2d = (
            self._project_world_point(projector_origin, view_context)
            if projector_origin is not None
            else None
        )
        clamp_origin_2d = (
            self._project_world_point(clamp_origin, view_context)
            if clamp_origin is not None
            else None
        )
        camera_lens_origin_2d = (
            self._project_world_point(camera_lens_origin, view_context)
            if camera_lens_origin is not None
            else None
        )

        def draw_hit_marker(point: QPointF, world: Vec3, color: QColor, label: str) -> None:
            coord_text = f"({world[0]:.2f}, {world[1]:.2f}, {world[2]:.2f})"
            painter.save()
            painter.setPen(QPen(QColor(0, 0, 0, 230), 1.0))
            fill = QColor(color)
            fill.setAlpha(235)
            painter.setBrush(fill)
            painter.drawEllipse(point, 3.6, 3.6)
            painter.setPen(QColor(0, 0, 0, 220))
            painter.drawText(point + QPointF(7.0, -5.0), label)
            painter.drawText(point + QPointF(7.0, 9.0), coord_text)
            painter.setPen(color)
            painter.drawText(point + QPointF(6.0, -6.0), label)
            painter.drawText(point + QPointF(6.0, 8.0), coord_text)
            painter.restore()

        if projector_hit_2d is not None and projector_hit is not None:
            draw_hit_marker(projector_hit_2d, projector_hit, QColor(255, 190, 90), "Proj hit")
        if clamp_hit_2d is not None and clamp_hit is not None:
            draw_hit_marker(clamp_hit_2d, clamp_hit, QColor(92, 222, 255), "Scan hit")
        if projector_origin_2d is not None and projector_origin is not None:
            draw_hit_marker(
                projector_origin_2d,
                projector_origin,
                QColor(255, 146, 56),
                "Proj origin",
            )
        if clamp_origin_2d is not None and clamp_origin is not None:
            draw_hit_marker(
                clamp_origin_2d,
                clamp_origin,
                QColor(56, 180, 255),
                "Telecentric lens",
            )
        if camera_lens_origin_2d is not None and camera_lens_origin is not None:
            draw_hit_marker(
                camera_lens_origin_2d,
                camera_lens_origin,
                QColor(92, 222, 255),
                "Camera lens",
            )

    def _projected_surface_quad(
        self,
        center: Vec3,
        width: float,
        height: float,
        viewport_width: int,
        viewport_height: int,
        *,
        context: CameraContext | None = None,
    ) -> QPolygonF | None:
        if width <= 0 or height <= 0:
            return None
        if context is None:
            context = self._camera_projection_context(viewport_width, viewport_height)
        if context is None:
            return None

        projected: list[QPointF] = []
        for world_point in self._surface_world_corners(center, width, height):
            projected_point = self._project_world_point(world_point, context)
            if projected_point is None:
                return None
            projected.append(projected_point)
        return QPolygonF(projected)

    def _surface_camera_view_context(
        self, viewport_width: int, viewport_height: int
    ) -> CameraContext | None:
        telecentric_origin = self._surface_telecentric_lens_center_world()
        if telecentric_origin is None:
            return None
        forward = self._horizontal_forward_direction(telecentric_origin)
        look_at = (
            telecentric_origin[0] + forward[0],
            telecentric_origin[1] + forward[1],
            telecentric_origin[2] + forward[2],
        )
        return self._camera_projection_context_for_viewport(
            telecentric_origin,
            look_at,
            viewport_width,
            viewport_height,
            self._effective_projector_fov_deg(),
        )

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
                    capture = self.render_surface_camera_capture(width, height)
                    writer.append_data(self._qimage_to_rgb_array(capture))
        finally:
            self._processed = previous_processed
            self.update()

    def render_surface_camera_capture(self, width: int, height: int) -> QImage:
        pixmap = QPixmap.fromImage(self._processed)
        capture, _ = self._render_surface_camera_capture(
            pixmap,
            max(2, width),
            max(2, height),
        )
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

        out_of_frame = False
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

    def _plane_center(self) -> Vec3:
        delta = self.distance_m - self._base_distance_m
        d = self._plane_shift_direction
        return (
            self._base_plane_center[0] + d[0] * delta,
            self._base_plane_center[1] + d[1] * delta,
            self._base_plane_center[2] + d[2] * delta,
        )

    def _field_center(self) -> Vec3:
        frame = self._field_object_frame()
        if frame is None:
            return (self.field_center_x, self.field_center_y, self.field_center_z)
        plane_center, _, _, normal = frame
        offset = FIELD_OBJECT_PLANE_GAP_M + self._field_object_depth() * 0.5
        return (
            plane_center[0] + normal[0] * offset,
            plane_center[1] + normal[1] * offset,
            plane_center[2] + normal[2] * offset,
        )

    def _primary_projection_surface(self) -> tuple[Vec3, float, float] | None:
        if self.project_projection_plane:
            return (self._plane_center(), self.plane_width_m, self.plane_height_m)
        if self.project_field_object:
            return (self._field_center(), self.field_width_m, self.field_height_m)
        return None

    def _active_projection_centers(self) -> list[Vec3]:
        centers: list[Vec3] = []
        if self.project_projection_plane:
            centers.append(self._plane_center())
        if self.project_field_object:
            centers.append(self._field_center())
        if not centers:
            centers.append(self._plane_center())
        return centers

    def _look_target(self) -> Vec3:
        centers = self._active_projection_centers()
        count = float(len(centers))
        return (
            sum(c[0] for c in centers) / count,
            sum(c[1] for c in centers) / count,
            sum(c[2] for c in centers) / count,
        )

    def _sync_orbit_from_camera(self) -> None:
        offset = vec_subtract(
            (self.camera_x, self.camera_y, self.camera_z),
            self._orbit_target,
        )
        radius = math.sqrt(vec_dot(offset, offset))
        if radius <= 1e-6:
            radius = 1.0
            offset = (0.0, -1.0, 0.0)

        self._orbit_radius = radius
        self._orbit_azimuth = math.atan2(offset[1], offset[0])
        horizontal = math.sqrt(offset[0] * offset[0] + offset[1] * offset[1])
        self._orbit_elevation = math.atan2(offset[2], horizontal)

    def _apply_orbit_to_camera(self) -> None:
        cos_elevation = math.cos(self._orbit_elevation)
        tx, ty, tz = self._orbit_target
        self.camera_x = tx + self._orbit_radius * cos_elevation * math.cos(self._orbit_azimuth)
        self.camera_y = ty + self._orbit_radius * cos_elevation * math.sin(self._orbit_azimuth)
        self.camera_z = tz + self._orbit_radius * math.sin(self._orbit_elevation)

    def _rotate_plane_point(self, point: Vec3, plane_center: Vec3) -> Vec3:
        yaw = math.radians(self.yaw_deg)
        pitch = math.radians(self.pitch_deg)
        roll = math.radians(self.roll_deg)
        cyaw, syaw = math.cos(yaw), math.sin(yaw)
        cpitch, spitch = math.cos(pitch), math.sin(pitch)
        croll, sroll = math.cos(roll), math.sin(roll)

        x = point[0] - plane_center[0]
        y = point[1] - plane_center[1]
        z = point[2] - plane_center[2]

        # Rotation order: yaw(Z) -> pitch(X) -> roll(Y)
        x1, y1, z1 = (
            cyaw * x - syaw * y,
            syaw * x + cyaw * y,
            z,
        )
        x2, y2, z2 = (
            x1,
            cpitch * y1 - spitch * z1,
            spitch * y1 + cpitch * z1,
        )
        x3, y3, z3 = (
            croll * x2 + sroll * z2,
            y2,
            -sroll * x2 + croll * z2,
        )
        return (
            x3 + plane_center[0],
            y3 + plane_center[1],
            z3 + plane_center[2],
        )

    def _camera_projection_context(
        self, viewport_width: int, viewport_height: int
    ) -> CameraContext | None:
        return self._camera_projection_context_for_viewport(
            (self.camera_x, self.camera_y, self.camera_z),
            self._orbit_target,
            viewport_width,
            viewport_height,
            self.fov_deg,
        )

    def _camera_projection_context_for_viewport(
        self,
        camera: Vec3,
        look_at: Vec3,
        viewport_width: int,
        viewport_height: int,
        fov_deg: float,
    ) -> CameraContext | None:
        world_up: Vec3 = (0.0, 0.0, 1.0)

        forward = vec_normalize(vec_subtract(look_at, camera))
        if forward is None:
            return None
        if abs(vec_dot(forward, world_up)) > 0.98:
            world_up = (0.0, 1.0, 0.0)
        right = vec_normalize(vec_cross(forward, world_up))
        if right is None:
            return None
        up = vec_cross(right, forward)

        focal = (viewport_height / 2.0) / math.tan(math.radians(fov_deg) / 2.0)
        cx = viewport_width / 2.0
        cy_screen = viewport_height / 2.0
        return (camera, right, up, forward, focal, cx, cy_screen)

    def _world_to_camera(
        self,
        world_point: Vec3,
        context: CameraContext,
    ) -> Vec3:
        camera, right, up, forward, _, _, _ = context
        rel = vec_subtract(world_point, camera)
        return (vec_dot(rel, right), vec_dot(rel, up), vec_dot(rel, forward))

    def _project_camera_point(
        self,
        camera_point: Vec3,
        context: CameraContext,
    ) -> QPointF | None:
        _, _, _, _, focal, cx, cy_screen = context
        x_cam, y_cam, z_cam = camera_point
        if z_cam <= 1e-6:
            return None
        sx = cx + (focal * x_cam / z_cam)
        sy = cy_screen - (focal * y_cam / z_cam)
        return QPointF(sx, sy)

    def _project_world_point(
        self,
        world_point: Vec3,
        context: CameraContext,
    ) -> QPointF | None:
        camera_point = self._world_to_camera(world_point, context)
        return self._project_camera_point(camera_point, context)

    def _project_segment_clipped(
        self,
        start: Vec3,
        end: Vec3,
        context: CameraContext,
    ) -> tuple[QPointF, QPointF] | None:
        near = 1e-3
        a = self._world_to_camera(start, context)
        b = self._world_to_camera(end, context)

        if a[2] <= near and b[2] <= near:
            return None
        if a[2] <= near or b[2] <= near:
            az = a[2]
            bz = b[2]
            if abs(bz - az) <= 1e-9:
                return None
            t = (near - az) / (bz - az)
            intersection = (
                a[0] + t * (b[0] - a[0]),
                a[1] + t * (b[1] - a[1]),
                near,
            )
            if a[2] <= near:
                a = intersection
            else:
                b = intersection

        pa = self._project_camera_point(a, context)
        pb = self._project_camera_point(b, context)
        if pa is None or pb is None:
            return None
        return (pa, pb)

    def _draw_ground_grid(
        self, painter: QPainter, viewport_width: int, viewport_height: int
    ) -> None:
        context = self._camera_projection_context(viewport_width, viewport_height)
        if context is None:
            return
        steps = int(self.grid_extent / self.grid_step)
        if steps <= 0:
            return

        minor_pen = QPen(QColor(55, 55, 55), 1)
        major_pen = QPen(QColor(95, 95, 95), 1)
        axis_pen = QPen(QColor(150, 150, 150), 2)

        def draw_segment(a: Vec3, b: Vec3, pen: QPen) -> None:
            projected_segment = self._project_segment_clipped(a, b, context)
            if projected_segment is None:
                return
            pa, pb = projected_segment
            painter.setPen(pen)
            painter.drawLine(pa, pb)

        for i in range(-steps, steps + 1):
            coord = i * self.grid_step
            pen = minor_pen
            if i == 0:
                pen = axis_pen
            elif i % self.grid_major_every == 0:
                pen = major_pen

            draw_segment(
                (coord, -self.grid_extent, 0.0),
                (coord, self.grid_extent, 0.0),
                pen,
            )
            draw_segment(
                (-self.grid_extent, coord, 0.0),
                (self.grid_extent, coord, 0.0),
                pen,
            )

        axis_length = min(self.grid_extent * 0.35, max(self.grid_step * 3.0, 6.0))
        x_axis_segment = self._project_segment_clipped((0.0, 0.0, 0.0), (axis_length, 0.0, 0.0), context)
        if x_axis_segment is not None:
            painter.setPen(QPen(QColor(235, 70, 70), 2.5))
            pa, pb = x_axis_segment
            painter.drawLine(pa, pb)
        y_axis_segment = self._project_segment_clipped((0.0, 0.0, 0.0), (0.0, axis_length, 0.0), context)
        if y_axis_segment is not None:
            painter.setPen(QPen(QColor(80, 220, 90), 2.5))
            pa, pb = y_axis_segment
            painter.drawLine(pa, pb)

        painter.save()
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        def format_marker(value: float) -> str:
            if abs(value) <= 1e-9:
                return "0"
            rounded = round(value)
            if abs(value - rounded) <= 1e-9:
                return str(int(rounded))
            return f"{value:.1f}".rstrip("0").rstrip(".")

        def draw_marker(candidates: list[Vec3], text: str, offset: QPointF) -> None:
            for world_point in candidates:
                screen_point = self._project_world_point(world_point, context)
                if screen_point is None:
                    continue
                painter.setPen(QColor(0, 0, 0, 220))
                painter.drawText(screen_point + offset + QPointF(1.0, 1.0), text)
                painter.setPen(QColor(190, 190, 190))
                painter.drawText(screen_point + offset, text)
                return

        for i in range(-steps, steps + 1):
            if i != 0 and i % self.grid_major_every != 0:
                continue
            coord = i * self.grid_step
            label = format_marker(coord)
            draw_marker(
                [
                    (coord, self.grid_extent, 0.0),
                    (coord, -self.grid_extent, 0.0),
                ],
                label,
                QPointF(4.0, -4.0),
            )
            draw_marker(
                [
                    (self.grid_extent, coord, 0.0),
                    (-self.grid_extent, coord, 0.0),
                ],
                label,
                QPointF(4.0, 12.0),
            )

        x_label_point = self._project_world_point((axis_length, 0.0, 0.0), context)
        if x_label_point is not None:
            painter.setPen(QColor(0, 0, 0, 220))
            painter.drawText(x_label_point + QPointF(7.0, -5.0), "X")
            painter.setPen(QColor(235, 70, 70))
            painter.drawText(x_label_point + QPointF(6.0, -6.0), "X")
        y_label_point = self._project_world_point((0.0, axis_length, 0.0), context)
        if y_label_point is not None:
            painter.setPen(QColor(0, 0, 0, 220))
            painter.drawText(y_label_point + QPointF(7.0, -5.0), "Y")
            painter.setPen(QColor(80, 220, 90))
            painter.drawText(y_label_point + QPointF(6.0, -6.0), "Y")
        painter.restore()

    def _draw_oriented_box(
        self,
        painter: QPainter,
        context: CameraContext,
        origin: Vec3,
        look_target: Vec3,
        box_color: QColor,
        label: str,
        *,
        solid: bool = False,
        ground_to_world: bool = False,
        ground_world_z: float = 0.0,
        width: float | None = None,
        height: float | None = None,
        depth: float | None = None,
    ) -> None:
        w = self.projector_width if width is None else width
        h = self.projector_height if height is None else height
        d = self.projector_depth if depth is None else depth
        forward = vec_normalize(vec_subtract(look_target, origin))
        if forward is None:
            return
        world_up: Vec3 = (0.0, 0.0, 1.0)
        if abs(vec_dot(forward, world_up)) > 0.98:
            world_up = (0.0, 1.0, 0.0)
        right = vec_normalize(vec_cross(world_up, forward))
        if right is None:
            return
        up = vec_cross(forward, right)
        local_y_offset = 0.0
        if ground_to_world:
            local_y_offset = self._ground_alignment_local_y_offset(
                origin,
                up,
                -h / 2.0,
                target_world_z=ground_world_z,
            )

        def local_to_world(lx: float, ly: float, lz: float) -> Vec3:
            local_y = ly + local_y_offset
            return (
                origin[0] + right[0] * lx + up[0] * local_y + forward[0] * lz,
                origin[1] + right[1] * lx + up[1] * local_y + forward[1] * lz,
                origin[2] + right[2] * lx + up[2] * local_y + forward[2] * lz,
            )

        corners: list[Vec3] = [
            local_to_world(-w / 2, -h / 2, 0.0),
            local_to_world(w / 2, -h / 2, 0.0),
            local_to_world(w / 2, h / 2, 0.0),
            local_to_world(-w / 2, h / 2, 0.0),
            local_to_world(-w / 2, -h / 2, d),
            local_to_world(w / 2, -h / 2, d),
            local_to_world(w / 2, h / 2, d),
            local_to_world(-w / 2, h / 2, d),
        ]

        edges = [
            (0, 1),
            (1, 2),
            (2, 3),
            (3, 0),
            (4, 5),
            (5, 6),
            (6, 7),
            (7, 4),
            (0, 4),
            (1, 5),
            (2, 6),
            (3, 7),
        ]

        box_pen = QPen(box_color, 2)
        if solid:
            faces = [
                (0, 1, 2, 3),
                (4, 5, 6, 7),
                (0, 1, 5, 4),
                (1, 2, 6, 5),
                (2, 3, 7, 6),
                (3, 0, 4, 7),
            ]
            face_polygons: list[tuple[float, QPolygonF]] = []
            for face in faces:
                world_face = [corners[i] for i in face]
                projected_face: list[QPointF] = []
                for point in world_face:
                    projected_point = self._project_world_point(point, context)
                    if projected_point is None:
                        projected_face = []
                        break
                    projected_face.append(projected_point)
                if len(projected_face) != 4:
                    continue
                avg_depth = sum(self._world_to_camera(p, context)[2] for p in world_face) / 4.0
                face_polygons.append((avg_depth, QPolygonF(projected_face)))
            face_polygons.sort(key=lambda item: item[0], reverse=True)

            painter.save()
            fill_color = QColor(box_color)
            fill_color.setAlpha(95)
            painter.setBrush(fill_color)
            painter.setPen(QPen(box_color, 1))
            for _, polygon in face_polygons:
                painter.drawPolygon(polygon)
            painter.restore()
        else:
            painter.setPen(box_pen)
            for i0, i1 in edges:
                projected_segment = self._project_segment_clipped(
                    corners[i0], corners[i1], context
                )
                if projected_segment is None:
                    continue
                pa, pb = projected_segment
                painter.drawLine(pa, pb)

        label_anchor = self._project_world_point(corners[6], context)
        if label_anchor is None:
            label_anchor = self._project_world_point(origin, context)
        if label_anchor is not None:
            painter.save()
            font = painter.font()
            font.setPointSize(9)
            painter.setFont(font)
            painter.setPen(QColor(0, 0, 0, 220))
            painter.drawText(label_anchor + QPointF(7.0, -5.0), label)
            painter.setPen(box_color)
            painter.drawText(label_anchor + QPointF(6.0, -6.0), label)
            painter.restore()

    def _draw_projector_holder(
        self,
        painter: QPainter,
        context: CameraContext,
        origin: Vec3,
        look_target: Vec3,
    ) -> None:
        holder_width = PROJECTOR_HOLDER_OUTER_SIZE_CM
        holder_depth = PROJECTOR_HOLDER_OUTER_SIZE_CM
        holder_height = PROJECTOR_HOLDER_OUTER_HEIGHT_CM
        inner_size = PROJECTOR_HOLDER_INNER_SIZE_CM
        lip_drop = PROJECTOR_HOLDER_INNER_DROP_CM

        forward = vec_normalize(vec_subtract(look_target, origin))
        if forward is None:
            return
        holder_min_z = (self.projector_depth * 0.5) - (holder_depth * 0.5)
        holder_origin: Vec3 = (
            origin[0] + forward[0] * holder_min_z,
            origin[1] + forward[1] * holder_min_z,
            origin[2] + forward[2] * holder_min_z,
        )

        holder_color = QColor(125, 132, 142)
        self._draw_oriented_box(
            painter,
            context,
            holder_origin,
            look_target,
            holder_color,
            "Projector Holder",
            solid=True,
            ground_to_world=True,
            ground_world_z=0.0,
            width=holder_width,
            height=holder_height,
            depth=holder_depth,
        )

        world_up: Vec3 = (0.0, 0.0, 1.0)
        if abs(vec_dot(forward, world_up)) > 0.98:
            world_up = (0.0, 1.0, 0.0)
        right = vec_normalize(vec_cross(world_up, forward))
        if right is None:
            return
        up = vec_cross(forward, right)
        local_y_offset = self._ground_alignment_local_y_offset(
            holder_origin,
            up,
            -holder_height / 2.0,
            target_world_z=0.0,
        )

        def local_to_world(lx: float, ly: float, lz: float) -> Vec3:
            local_y = ly + local_y_offset
            return (
                holder_origin[0] + right[0] * lx + up[0] * local_y + forward[0] * lz,
                holder_origin[1] + right[1] * lx + up[1] * local_y + forward[1] * lz,
                holder_origin[2] + right[2] * lx + up[2] * local_y + forward[2] * lz,
            )

        outer_top_y = holder_height / 2.0
        inner_bottom_y = outer_top_y - lip_drop
        inner_w = inner_size
        inner_d = inner_size
        inner_z0 = (holder_depth - inner_d) * 0.5
        inner_z1 = inner_z0 + inner_d
        outer = [
            local_to_world(-holder_width / 2.0, outer_top_y, 0.0),
            local_to_world(holder_width / 2.0, outer_top_y, 0.0),
            local_to_world(holder_width / 2.0, outer_top_y, holder_depth),
            local_to_world(-holder_width / 2.0, outer_top_y, holder_depth),
        ]
        inner_top = [
            local_to_world(-inner_w / 2.0, outer_top_y, inner_z0),
            local_to_world(inner_w / 2.0, outer_top_y, inner_z0),
            local_to_world(inner_w / 2.0, outer_top_y, inner_z1),
            local_to_world(-inner_w / 2.0, outer_top_y, inner_z1),
        ]
        inner_bottom = [
            local_to_world(-inner_w / 2.0, inner_bottom_y, inner_z0),
            local_to_world(inner_w / 2.0, inner_bottom_y, inner_z0),
            local_to_world(inner_w / 2.0, inner_bottom_y, inner_z1),
            local_to_world(-inner_w / 2.0, inner_bottom_y, inner_z1),
        ]

        painter.save()
        painter.setPen(QPen(QColor(178, 186, 198), 1.3))
        for i in range(4):
            outer_seg = self._project_segment_clipped(outer[i], outer[(i + 1) % 4], context)
            if outer_seg is not None:
                pa, pb = outer_seg
                painter.drawLine(pa, pb)
            inner_top_seg = self._project_segment_clipped(
                inner_top[i], inner_top[(i + 1) % 4], context
            )
            if inner_top_seg is not None:
                pa, pb = inner_top_seg
                painter.drawLine(pa, pb)
            inner_bottom_seg = self._project_segment_clipped(
                inner_bottom[i], inner_bottom[(i + 1) % 4], context
            )
            if inner_bottom_seg is not None:
                pa, pb = inner_bottom_seg
                painter.drawLine(pa, pb)
            inner_wall_seg = self._project_segment_clipped(
                inner_top[i], inner_bottom[i], context
            )
            if inner_wall_seg is not None:
                pa, pb = inner_wall_seg
                painter.drawLine(pa, pb)
            top_rim_seg = self._project_segment_clipped(
                outer[i], inner_top[i], context
            )
            if top_rim_seg is not None:
                pa, pb = top_rim_seg
                painter.drawLine(pa, pb)
        painter.restore()

    def _draw_surface_camera_mount(
        self,
        painter: QPainter,
        context: CameraContext,
        origin: Vec3,
        look_target: Vec3,
        mount_color: QColor,
        label: str,
    ) -> Vec3 | None:
        forward = vec_normalize(vec_subtract(look_target, origin))
        if forward is None:
            return None
        world_up: Vec3 = (0.0, 0.0, 1.0)
        if abs(vec_dot(forward, world_up)) > 0.98:
            world_up = (0.0, 1.0, 0.0)
        right = vec_normalize(vec_cross(world_up, forward))
        if right is None:
            return None
        up = vec_cross(forward, right)
        ground_align_local_y = 0.0
        if abs(up[2]) > 1e-6:
            ground_align_local_y = -origin[2] / up[2]

        def local_to_world(lx: float, ly: float, lz: float) -> Vec3:
            local_y = ly + ground_align_local_y
            return (
                origin[0] + right[0] * lx + up[0] * local_y + forward[0] * lz,
                origin[1] + right[1] * lx + up[1] * local_y + forward[1] * lz,
                origin[2] + right[2] * lx + up[2] * local_y + forward[2] * lz,
            )

        def draw_prism(
            local_corners: list[tuple[float, float, float]],
            color: QColor,
            fill_alpha: int,
        ) -> None:
            world_corners = [local_to_world(*corner) for corner in local_corners]
            faces = [
                (0, 1, 2, 3),
                (4, 5, 6, 7),
                (0, 1, 5, 4),
                (1, 2, 6, 5),
                (2, 3, 7, 6),
                (3, 0, 4, 7),
            ]
            edges = [
                (0, 1),
                (1, 2),
                (2, 3),
                (3, 0),
                (4, 5),
                (5, 6),
                (6, 7),
                (7, 4),
                (0, 4),
                (1, 5),
                (2, 6),
                (3, 7),
            ]
            face_polygons: list[tuple[float, QPolygonF]] = []
            for face in faces:
                world_face = [world_corners[i] for i in face]
                projected_face: list[QPointF] = []
                for point in world_face:
                    projected_point = self._project_world_point(point, context)
                    if projected_point is None:
                        projected_face = []
                        break
                    projected_face.append(projected_point)
                if len(projected_face) != 4:
                    continue
                avg_depth = sum(self._world_to_camera(p, context)[2] for p in world_face) / 4.0
                face_polygons.append((avg_depth, QPolygonF(projected_face)))
            face_polygons.sort(key=lambda item: item[0], reverse=True)

            painter.save()
            fill = QColor(color)
            fill.setAlpha(fill_alpha)
            painter.setBrush(fill)
            painter.setPen(QPen(color, 1))
            for _, polygon in face_polygons:
                painter.drawPolygon(polygon)
            painter.restore()

            painter.save()
            painter.setPen(QPen(color, 1.5))
            for i0, i1 in edges:
                projected_segment = self._project_segment_clipped(
                    world_corners[i0], world_corners[i1], context
                )
                if projected_segment is None:
                    continue
                pa, pb = projected_segment
                painter.drawLine(pa, pb)
            painter.restore()
        outer_w = SURFACE_CLAMP_OUTER_CIRCLE_DIAMETER_CM
        outer_arch_radius = outer_w * 0.5
        total_h = SURFACE_CLAMP_TOTAL_HEIGHT_CM
        bottom_y = 0.0
        arch_base_y = bottom_y + total_h - outer_arch_radius
        bottom_rect_top = bottom_y + SURFACE_CLAMP_BOTTOM_RECT_HEIGHT_CM
        front_z = SURFACE_CLAMP_THICKNESS_CM * 0.5
        back_z = -SURFACE_CLAMP_THICKNESS_CM * 0.5

        arc_segments = 24
        outer_profile: list[tuple[float, float]] = [
            (-outer_w * 0.5, bottom_y),
            (outer_w * 0.5, bottom_y),
            (outer_w * 0.5, arch_base_y),
        ]
        for i in range(arc_segments + 1):
            theta = math.pi * (i / arc_segments)
            outer_profile.append(
                (
                    math.cos(theta) * outer_arch_radius,
                    arch_base_y + math.sin(theta) * outer_arch_radius,
                )
            )
        outer_profile.append((-outer_w * 0.5, arch_base_y))

        hole_radius = SURFACE_CLAMP_INNER_CIRCLE_DIAMETER_CM * 0.5
        hole_center_y = SURFACE_CLAMP_CIRCLE_CENTER_HEIGHT_CM
        aperture_center_world = local_to_world(0.0, hole_center_y, (front_z + back_z) * 0.5)
        hole_segments = 28
        hole_profile: list[tuple[float, float]] = []
        for i in range(hole_segments):
            theta = (2.0 * math.pi * i) / hole_segments
            hole_profile.append(
                (math.cos(theta) * hole_radius, hole_center_y + math.sin(theta) * hole_radius)
            )

        def project_loop(
            profile: list[tuple[float, float]],
            z: float,
        ) -> tuple[list[Vec3], list[QPointF]] | None:
            world_points = [local_to_world(px, py, z) for px, py in profile]
            projected_points: list[QPointF] = []
            for point in world_points:
                screen_point = self._project_world_point(point, context)
                if screen_point is None:
                    return None
                projected_points.append(screen_point)
            return (world_points, projected_points)

        outer_front = project_loop(outer_profile, front_z)
        outer_back = project_loop(outer_profile, back_z)
        hole_front = project_loop(hole_profile, front_z)
        hole_back = project_loop(hole_profile, back_z)
        if (
            outer_front is None
            or outer_back is None
            or hole_front is None
            or hole_back is None
        ):
            return None

        outer_front_world, outer_front_2d = outer_front
        outer_back_world, outer_back_2d = outer_back
        hole_front_world, hole_front_2d = hole_front
        hole_back_world, hole_back_2d = hole_back

        def draw_window_face(
            outer: list[QPointF],
            hole: list[QPointF],
            color: QColor,
            alpha: int,
        ) -> None:
            path = QPainterPath()
            path.setFillRule(Qt.FillRule.OddEvenFill)
            path.addPolygon(QPolygonF(outer))
            path.addPolygon(QPolygonF(list(reversed(hole))))
            painter.save()
            fill = QColor(color)
            fill.setAlpha(alpha)
            painter.fillPath(path, fill)
            painter.setPen(QPen(color, 1.3))
            painter.drawPolygon(QPolygonF(outer))
            painter.drawPolygon(QPolygonF(hole))
            painter.restore()

        back_color = QColor(75, 106, 130)
        draw_window_face(outer_back_2d, hole_back_2d, back_color, 110)
        draw_window_face(outer_front_2d, hole_front_2d, mount_color, 145)

        # Bottom rectangular section boundary (25.10mm from ground).
        seam_front = self._project_segment_clipped(
            local_to_world(-outer_w * 0.5, bottom_rect_top, front_z),
            local_to_world(outer_w * 0.5, bottom_rect_top, front_z),
            context,
        )
        seam_back = self._project_segment_clipped(
            local_to_world(-outer_w * 0.5, bottom_rect_top, back_z),
            local_to_world(outer_w * 0.5, bottom_rect_top, back_z),
            context,
        )
        painter.save()
        painter.setPen(QPen(QColor(125, 165, 195), 1.2))
        if seam_back is not None:
            pa, pb = seam_back
            painter.drawLine(pa, pb)
        if seam_front is not None:
            pa, pb = seam_front
            painter.drawLine(pa, pb)
        painter.restore()

        painter.save()
        painter.setPen(QPen(QColor(110, 150, 180), 1))
        for i in range(len(outer_front_world)):
            segment = self._project_segment_clipped(
                outer_front_world[i],
                outer_back_world[i],
                context,
            )
            if segment is None:
                continue
            pa, pb = segment
            painter.drawLine(pa, pb)

        for i in range(0, len(hole_front_world), 2):
            segment = self._project_segment_clipped(
                hole_front_world[i],
                hole_back_world[i],
                context,
            )
            if segment is None:
                continue
            pa, pb = segment
            painter.drawLine(pa, pb)
        painter.restore()

        label_point_world = local_to_world(0.0, arch_base_y + outer_arch_radius, front_z)

        label_anchor = self._project_world_point(label_point_world, context)
        if label_anchor is None:
            label_anchor = self._project_world_point(origin, context)
        if label_anchor is not None:
            painter.save()
            font = painter.font()
            font.setPointSize(9)
            painter.setFont(font)
            painter.setPen(QColor(0, 0, 0, 220))
            painter.drawText(label_anchor + QPointF(7.0, -5.0), label)
            painter.setPen(mount_color)
            painter.drawText(label_anchor + QPointF(6.0, -6.0), label)
            painter.restore()
        return aperture_center_world

    def _draw_device_boxes(
        self, painter: QPainter, viewport_width: int, viewport_height: int
    ) -> None:
        self._clamp_projection_hit_world = None
        self._clamp_ray_origin_world = None
        context = self._camera_projection_context(viewport_width, viewport_height)
        if context is None:
            return

        w = self.projector_width
        h = self.projector_height
        d = self.projector_depth
        if w <= 0 or h <= 0 or d <= 0:
            return

        projector_origin: Vec3 = (
            self._projector_pos[0],
            self._projector_pos[1],
            self._projector_pos[2],
        )
        surface_camera_origin: Vec3 = (
            self._surface_camera_pos[0],
            self._surface_camera_pos[1],
            self._surface_camera_pos[2],
        )
        projector_look_target = self._projector_horizontal_target(projector_origin)
        surface_camera_look_target = self._projector_horizontal_target(surface_camera_origin)
        self._draw_projector_holder(
            painter,
            context,
            projector_origin,
            projector_look_target,
        )
        self._draw_oriented_box(
            painter,
            context,
            projector_origin,
            projector_look_target,
            QColor(255, 146, 56),
            "Projector",
            solid=True,
            ground_to_world=True,
            ground_world_z=PROJECTOR_HOLDER_HEIGHT_CM,
        )
        aperture_center = self._draw_surface_camera_mount(
            painter,
            context,
            surface_camera_origin,
            surface_camera_look_target,
            QColor(56, 180, 255),
            "56027 Clamp",
        )
        if aperture_center is None:
            return
        self._clamp_ray_origin_world = aperture_center
        projection_surface = self._primary_projection_surface()
        if projection_surface is None:
            return
        surface_center, surface_width, surface_height = projection_surface
        surface_world = self._surface_world_corners(surface_center, surface_width, surface_height)
        edge_u = vec_subtract(surface_world[1], surface_world[0])
        edge_v = vec_subtract(surface_world[3], surface_world[0])
        plane_normal = vec_normalize(vec_cross(edge_u, edge_v))
        clamp_ray_target = self._projector_horizontal_target(aperture_center)
        camera_axis_target = vec_normalize(vec_subtract(clamp_ray_target, aperture_center))
        ray_direction = camera_axis_target
        contour_hit: Vec3 | None = None
        if plane_normal is not None and ray_direction is not None:
            contour_hit = self._intersect_ray_with_plane(
                aperture_center,
                ray_direction,
                surface_world[0],
                plane_normal,
            )
        if contour_hit is None:
            contour_hit = surface_center
        self._clamp_projection_hit_world = contour_hit
        contour_segment = self._project_segment_clipped(aperture_center, contour_hit, context)
        if contour_segment is not None:
            painter.save()
            painter.setPen(QPen(QColor(92, 222, 255, 210), 1.5))
            pa, pb = contour_segment
            painter.drawLine(pa, pb)
            painter.restore()
