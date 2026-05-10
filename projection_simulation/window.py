import math

from PySide6.QtCore import QPointF, Qt, Slot
from PySide6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import QCheckBox, QFrame, QLabel, QSlider, QVBoxLayout, QWidget

from .math3d import vec_cross, vec_dot, vec_normalize, vec_subtract
from .types import CameraContext, Vec3

PROJECTOR_THROW_RATIO = 1.2
PROJECTOR_IMAGE_ASPECT = 16.0 / 9.0
PROJECTOR_BODY_SIZE_CM = 5.5
PROJECTOR_ANGLE_LIMIT_DEG = 45
DEFAULT_PROJECTION_ANGLE_DEG = -20.0
DEFAULT_DEVICE_SPACING_CM = 12.0
PROJECTOR_LENS_WINDOW_WIDTH_CM = 1.4
PROJECTOR_LENS_WINDOW_HEIGHT_CM = 1.0
PROJECTOR_LENS_FACE_EPS = 0.01
PROJECTOR_HOLDER_OUTER_SIZE_CM = 6.0  # 60mm
PROJECTOR_HOLDER_OUTER_HEIGHT_CM = 4.1  # 41mm
PROJECTOR_HOLDER_INNER_SIZE_CM = 5.5  # 55mm
PROJECTOR_HOLDER_INNER_DROP_CM = 0.75  # 7.5mm pocket depth
PROJECTOR_HOLDER_HEIGHT_CM = PROJECTOR_HOLDER_OUTER_HEIGHT_CM - PROJECTOR_HOLDER_INNER_DROP_CM  # 33.5mm seat height

# Edmund Optics 56027 drawing dimensions (mm converted to scene cm).
SURFACE_CLAMP_TOTAL_HEIGHT_CM = 14.8  # 148.00mm
SURFACE_CLAMP_BOTTOM_RECT_HEIGHT_CM = 2.51  # 25.10mm
SURFACE_CLAMP_CIRCLE_CENTER_HEIGHT_CM = 8.1  # 81.00mm from ground
SURFACE_CLAMP_THICKNESS_CM = 5.0  # 50.00mm (Y thickness from drawing)
SURFACE_CLAMP_OUTER_CIRCLE_DIAMETER_CM = 13.4  # 134.00mm
SURFACE_CLAMP_INNER_CIRCLE_DIAMETER_CM = 11.18  # 111.8mm


class ProjectionWindow(QWidget):
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
        show_projector: bool,
        projector_width: float,
        projector_height: float,
        projector_depth: float,
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
        self.show_projector = show_projector
        self.projector_width = projector_width
        self.projector_height = projector_height
        self.projector_depth = projector_depth
        self.projector_lens_offset_x = projector_lens_offset_x
        self.projector_lens_offset_y = projector_lens_offset_y
        self.projector_lens_offset_z = projector_lens_offset_z
        self.yaw_deg = yaw_deg
        self.pitch_deg = pitch_deg
        self.roll_deg = roll_deg
        self.show_proj_hit_marker = True
        self.show_clamp_hit_marker = True
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

    def _process_image(self, image: QImage) -> QImage:
        processed = image
        if self.force_landscape and processed.height() > processed.width():
            processed = processed.transformed(QTransform().rotate(90))
        if self.mirror_horizontal:
            processed = processed.mirrored(True, False)
        return processed

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
        look_target = self._projector_horizontal_target(origin)
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
        if abs(up[2]) <= 1e-6:
            return None
        ground_align_local_y = -origin[2] / up[2]
        hole_center_y = SURFACE_CLAMP_CIRCLE_CENTER_HEIGHT_CM
        return (
            origin[0] + up[0] * (hole_center_y + ground_align_local_y),
            origin[1] + up[1] * (hole_center_y + ground_align_local_y),
            origin[2] + up[2] * (hole_center_y + ground_align_local_y),
        )

    def _ray_origins_world(self) -> tuple[Vec3, Vec3] | None:
        lens_data = self._projector_lens_rectangle_world()
        if lens_data is None:
            return None
        _, projector_origin = lens_data
        clamp_origin = self._clamp_aperture_center_world(self._surface_camera_pos)
        if clamp_origin is None:
            return None
        return (projector_origin, clamp_origin)

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
        clamp_origin = self._clamp_aperture_center_world(self._surface_camera_pos)
        if clamp_origin is None:
            return None
        look_target = self._projector_horizontal_target(clamp_origin)
        direction = vec_normalize(vec_subtract(look_target, clamp_origin))
        return self._ray_angle_to_y_axis_deg(direction)

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
            clamp_origin = self._clamp_aperture_center_world(self._surface_camera_pos)
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
            "QCheckBox { color: #E6E6E6; }"
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
        self._ray_angles_label = QLabel(self._controls_frame)

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

        self._show_proj_hit_checkbox = QCheckBox("Show proj hit", self._controls_frame)
        self._show_proj_hit_checkbox.setChecked(self.show_proj_hit_marker)
        self._show_proj_hit_checkbox.toggled.connect(self._on_show_proj_hit_toggled)
        self._show_clamp_hit_checkbox = QCheckBox("Show clamp hit", self._controls_frame)
        self._show_clamp_hit_checkbox.setChecked(self.show_clamp_hit_marker)
        self._show_clamp_hit_checkbox.toggled.connect(self._on_show_clamp_hit_toggled)

        layout.addWidget(self._spacing_label)
        layout.addWidget(self._spacing_slider)
        layout.addWidget(self._distance_label)
        layout.addWidget(self._distance_slider)
        layout.addWidget(self._ray_angles_label)
        layout.addWidget(self._projector_fov_label)
        layout.addWidget(self._projector_fov_slider)
        layout.addWidget(self._lens_offset_x_label)
        layout.addWidget(self._lens_offset_x_slider)
        layout.addWidget(self._lens_offset_y_label)
        layout.addWidget(self._lens_offset_y_slider)
        layout.addWidget(self._show_proj_hit_checkbox)
        layout.addWidget(self._show_clamp_hit_checkbox)
        self._refresh_control_labels()
        self._controls_frame.setVisible(self.mode == "plane3d")

    def _refresh_control_labels(self) -> None:
        if hasattr(self, "_spacing_label"):
            self._spacing_label.setText(f"Proj-clamp spacing (ray origins): {self._device_spacing_cm:.1f} cm")
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
        if hasattr(self, "_ray_angles_label"):
            projector_angle = self._projector_ray_angle_to_y_axis_deg()
            clamp_angle = self._clamp_ray_angle_to_y_axis_deg()
            projector_text = f"{projector_angle:.1f}°" if projector_angle is not None else "n/a"
            clamp_text = f"{clamp_angle:.1f}°" if clamp_angle is not None else "n/a"
            self._ray_angles_label.setText(
                f"Ray angle vs +Y: Proj {projector_text}, Clamp {clamp_text}"
            )
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
        if hasattr(self, "_show_proj_hit_checkbox"):
            show_proj = bool(getattr(self, "show_proj_hit_marker", True))
            if self._show_proj_hit_checkbox.isChecked() != show_proj:
                self._show_proj_hit_checkbox.blockSignals(True)
                self._show_proj_hit_checkbox.setChecked(show_proj)
                self._show_proj_hit_checkbox.blockSignals(False)
        if hasattr(self, "_show_clamp_hit_checkbox"):
            show_clamp = bool(getattr(self, "show_clamp_hit_marker", True))
            if self._show_clamp_hit_checkbox.isChecked() != show_clamp:
                self._show_clamp_hit_checkbox.blockSignals(True)
                self._show_clamp_hit_checkbox.setChecked(show_clamp)
                self._show_clamp_hit_checkbox.blockSignals(False)

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

    @Slot(bool)
    def _on_show_proj_hit_toggled(self, checked: bool) -> None:
        self.show_proj_hit_marker = bool(checked)
        self.update()

    @Slot(bool)
    def _on_show_clamp_hit_toggled(self, checked: bool) -> None:
        self.show_clamp_hit_marker = bool(checked)
        self.update()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        if hasattr(self, "_controls_frame"):
            self._controls_frame.setGeometry(12, 12, 280, 330)
        super().resizeEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() in (Qt.Key_Escape, Qt.Key_Q):
            self.close()
            return
        super().keyPressEvent(event)

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
        painter.fillRect(self.rect(), Qt.black)

        pixmap = QPixmap.fromImage(self._processed)
        if self.mode == "plane3d":
            if self.show_ground_grid:
                self._draw_ground_grid(painter, self.width(), self.height())
            drew_projection = self._draw_plane3d_projection(painter, pixmap)
            if self.show_projector:
                self._draw_device_boxes(painter, self.width(), self.height())
                self._draw_projector_contours(
                    painter,
                    pixmap,
                    self.width(),
                    self.height(),
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

    def _draw_plane3d_projection(self, painter: QPainter, pixmap: QPixmap) -> bool:
        viewport_width = self.width()
        viewport_height = self.height()
        drew_any = False

        if self.project_projection_plane:
            projection_plane_quad = self._projected_surface_quad(
                self._plane_center(),
                self.plane_width_m,
                self.plane_height_m,
                viewport_width,
                viewport_height,
            )
            if projection_plane_quad is not None:
                self._draw_solid_quad(
                    painter,
                    projection_plane_quad,
                    QColor(56, 64, 82),
                )
                drew_any = True

        projection_surface = self._primary_projection_surface()
        if projection_surface is not None:
            center, width, height = projection_surface
            if self._draw_surface_projection(
                painter,
                pixmap,
                center,
                width,
                height,
                viewport_width,
                viewport_height,
            ):
                drew_any = True

        return drew_any

    def _draw_surface_projection(
        self,
        painter: QPainter,
        pixmap: QPixmap,
        center: Vec3,
        width: float,
        height: float,
        viewport_width: int,
        viewport_height: int,
    ) -> bool:
        projected = self._projected_projection_footprint(
            center,
            width,
            height,
            pixmap.width(),
            pixmap.height(),
            viewport_width,
            viewport_height,
        )
        if projected is None:
            return False
        projection_quad, surface_quad, _ = projected
        self._draw_projected_quad(
            painter,
            pixmap,
            projection_quad,
            clip_quad=surface_quad,
        )
        return True

    def _draw_projected_quad(
        self,
        painter: QPainter,
        pixmap: QPixmap,
        destination_quad: QPolygonF,
        *,
        clip_quad: QPolygonF | None = None,
    ) -> None:
        source_quad = QPolygonF(
            [
                QPointF(0.0, 0.0),
                QPointF(float(pixmap.width()), 0.0),
                QPointF(float(pixmap.width()), float(pixmap.height())),
                QPointF(0.0, float(pixmap.height())),
            ]
        )
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

    def _projector_horizontal_target(self, origin: Vec3) -> Vec3:
        target = self._look_target()
        primary_surface = self._primary_projection_surface()
        if primary_surface is not None:
            target = primary_surface[0]
        horizontal_target = (target[0], target[1], origin[2])
        if (
            abs(horizontal_target[0] - origin[0]) <= 1e-9
            and abs(horizontal_target[1] - origin[1]) <= 1e-9
        ):
            return target
        return horizontal_target

    def _ground_alignment_local_y_offset(
        self,
        origin: Vec3,
        up: Vec3,
        local_ground_y: float,
        target_world_z: float = 0.0,
    ) -> float:
        if abs(up[2]) <= 1e-6:
            return 0.0
        return ((target_world_z - origin[2]) / up[2]) - local_ground_y

    def _projector_chassis_axes(self) -> tuple[Vec3, Vec3, Vec3, Vec3] | None:
        chassis_origin = self._projector_pos
        forward = vec_normalize(
            vec_subtract(self._projector_horizontal_target(chassis_origin), chassis_origin)
        )
        if forward is None:
            return None
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

        half_body_w = self.projector_width / 2.0
        half_body_h = self.projector_height / 2.0
        lens_half_w = min(PROJECTOR_LENS_WINDOW_WIDTH_CM / 2.0, max(0.1, half_body_w - 0.05))
        lens_half_h = min(PROJECTOR_LENS_WINDOW_HEIGHT_CM / 2.0, max(0.1, half_body_h - 0.05))
        local_y_offset = self._ground_alignment_local_y_offset(
            chassis_origin,
            up,
            -half_body_h,
            target_world_z=PROJECTOR_HOLDER_HEIGHT_CM,
        )

        cx = max(-half_body_w + lens_half_w, min(half_body_w - lens_half_w, self.projector_lens_offset_x))
        cy = max(-half_body_h + lens_half_h, min(half_body_h - lens_half_h, self.projector_lens_offset_y))
        cz = self.projector_depth + PROJECTOR_LENS_FACE_EPS

        def local_to_world(lx: float, ly: float, lz: float) -> Vec3:
            local_y = ly + local_y_offset
            return (
                chassis_origin[0] + right[0] * lx + up[0] * local_y + forward[0] * lz,
                chassis_origin[1] + right[1] * lx + up[1] * local_y + forward[1] * lz,
                chassis_origin[2] + right[2] * lx + up[2] * local_y + forward[2] * lz,
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
        lens_forward = vec_normalize(
            vec_subtract(self._projector_horizontal_target(lens_origin), lens_origin)
        )
        if lens_forward is None:
            return None
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

    def _projected_projection_footprint(
        self,
        center: Vec3,
        width: float,
        height: float,
        image_width: int,
        image_height: int,
        viewport_width: int,
        viewport_height: int,
    ) -> tuple[QPolygonF, QPolygonF, list[Vec3]] | None:
        if width <= 0 or height <= 0:
            return None
        view_context = self._camera_projection_context(viewport_width, viewport_height)
        if view_context is None:
            return None
        projector_context = self._projector_projection_context(image_width, image_height)
        if projector_context is None:
            return None

        surface_world = self._surface_world_corners(center, width, height)
        surface_quad_points: list[QPointF] = []
        for world_corner in surface_world:
            screen_point = self._project_world_point(world_corner, view_context)
            if screen_point is None:
                return None
            surface_quad_points.append(screen_point)
        surface_quad = QPolygonF(surface_quad_points)

        edge_u = vec_subtract(surface_world[1], surface_world[0])
        edge_v = vec_subtract(surface_world[3], surface_world[0])
        plane_normal = vec_normalize(vec_cross(edge_u, edge_v))
        if plane_normal is None:
            return None

        projector_origin = projector_context[0]
        source_corners = [
            (0.0, 0.0),
            (float(image_width), 0.0),
            (float(image_width), float(image_height)),
            (0.0, float(image_height)),
        ]
        projection_points: list[QPointF] = []
        footprint_hits_world: list[Vec3] = []
        for sx, sy in source_corners:
            ray_direction = self._projector_ray_direction(
                sx, sy, image_width, image_height, projector_context
            )
            if ray_direction is None:
                return None
            hit = self._intersect_ray_with_plane(
                projector_origin, ray_direction, surface_world[0], plane_normal
            )
            if hit is None:
                return None
            screen_hit = self._project_world_point(hit, view_context)
            if screen_hit is None:
                return None
            projection_points.append(screen_hit)
            footprint_hits_world.append(hit)
        return (QPolygonF(projection_points), surface_quad, footprint_hits_world)

    def _draw_projector_contours(
        self,
        painter: QPainter,
        pixmap: QPixmap,
        viewport_width: int,
        viewport_height: int,
    ) -> None:
        self._projector_projection_hit_world = None
        self._projector_ray_origin_world = None
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

        def draw_contour_for_surface(center: Vec3, width: float, height: float) -> Vec3 | None:
            projected = self._projected_projection_footprint(
                center,
                width,
                height,
                pixmap.width(),
                pixmap.height(),
                viewport_width,
                viewport_height,
            )
            if projected is None:
                return None
            projection_quad, _, hit_world_points = projected

            for i in range(projection_quad.count()):
                pa = projection_quad.at(i)
                pb = projection_quad.at((i + 1) % projection_quad.count())
                painter.drawLine(pa, pb)

            for i, hit in enumerate(hit_world_points):
                lens_corner = lens_corners_world[i % len(lens_corners_world)]
                segment = self._project_segment_clipped(lens_corner, hit, view_context)
                if segment is None:
                    continue
                pa, pb = segment
                painter.drawLine(pa, pb)

            surface_world = self._surface_world_corners(center, width, height)
            edge_u = vec_subtract(surface_world[1], surface_world[0])
            edge_v = vec_subtract(surface_world[3], surface_world[0])
            plane_normal = vec_normalize(vec_cross(edge_u, edge_v))
            center_ray = self._projector_ray_direction(
                pixmap.width() * 0.5,
                pixmap.height() * 0.5,
                pixmap.width(),
                pixmap.height(),
                projector_context,
            )
            center_hit_world: Vec3 | None = None
            if plane_normal is not None and center_ray is not None:
                center_hit_world = self._intersect_ray_with_plane(
                    projector_context[0],
                    center_ray,
                    surface_world[0],
                    plane_normal,
                )
            if center_hit_world is not None:
                center_line = self._project_segment_clipped(
                    lens_center_world, center_hit_world, view_context
                )
                if center_line is not None:
                    painter.save()
                    painter.setPen(QPen(QColor(255, 190, 90, 210), 1.5))
                    pa, pb = center_line
                    painter.drawLine(pa, pb)
                    painter.restore()
                return center_hit_world
            return None

        projection_surface = self._primary_projection_surface()
        if projection_surface is None:
            return
        center, width, height = projection_surface
        projector_hit = draw_contour_for_surface(center, width, height)
        self._projector_projection_hit_world = projector_hit
        clamp_hit = getattr(self, "_clamp_projection_hit_world", None)

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
        clamp_origin = getattr(self, "_clamp_ray_origin_world", None)
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

        if (
            bool(getattr(self, "show_proj_hit_marker", True))
            and projector_hit_2d is not None
            and projector_hit is not None
        ):
            draw_hit_marker(projector_hit_2d, projector_hit, QColor(255, 190, 90), "Proj hit")
        if (
            bool(getattr(self, "show_clamp_hit_marker", True))
            and clamp_hit_2d is not None
            and clamp_hit is not None
        ):
            draw_hit_marker(clamp_hit_2d, clamp_hit, QColor(92, 222, 255), "Clamp hit")
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
                "Clamp origin",
            )

    def _projected_surface_quad(
        self,
        center: Vec3,
        width: float,
        height: float,
        viewport_width: int,
        viewport_height: int,
    ) -> QPolygonF | None:
        if width <= 0 or height <= 0:
            return None
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

    def _plane_center(self) -> Vec3:
        delta = self.distance_m - self._base_distance_m
        d = self._plane_shift_direction
        return (
            self._base_plane_center[0] + d[0] * delta,
            self._base_plane_center[1] + d[1] * delta,
            self._base_plane_center[2] + d[2] * delta,
        )

    def _field_center(self) -> Vec3:
        return (self.field_center_x, self.field_center_y, self.field_center_z)

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
        look_target = self._orbit_target
        camera: Vec3 = (self.camera_x, self.camera_y, self.camera_z)
        look_at = look_target
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

        focal = (viewport_height / 2.0) / math.tan(math.radians(self.fov_deg) / 2.0)
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
