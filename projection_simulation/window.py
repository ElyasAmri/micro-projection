import math

from PySide6.QtCore import QPointF, Qt
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
from PySide6.QtWidgets import QWidget

from .math3d import vec_cross, vec_dot, vec_normalize, vec_subtract
from .types import CameraContext, Vec3


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
        self.distance_m = distance_m
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
        self.yaw_deg = yaw_deg
        self.pitch_deg = pitch_deg
        self.roll_deg = roll_deg
        self._processed = self._process_image(image)
        self._orbit_target = self._look_target()
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

    def _process_image(self, image: QImage) -> QImage:
        processed = image
        if self.force_landscape and processed.height() > processed.width():
            processed = processed.transformed(QTransform().rotate(90))
        if self.mirror_horizontal:
            processed = processed.mirrored(True, False)
        return processed

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
            if self.show_projector:
                self._draw_device_boxes(painter, self.width(), self.height())
            if self._draw_plane3d_projection(painter, pixmap):
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

        if self.project_field_object:
            field_quad = self._projected_surface_quad(
                self._field_center(),
                self.field_width_m,
                self.field_height_m,
                viewport_width,
                viewport_height,
            )
            if field_quad is not None:
                self._draw_projected_quad(painter, pixmap, field_quad)
                drew_any = True

        return drew_any

    def _draw_projected_quad(
        self, painter: QPainter, pixmap: QPixmap, destination_quad: QPolygonF
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
        clip_path.addPolygon(destination_quad)
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
        for corner in self._surface_corners(center, width, height):
            world_point = self._rotate_plane_point(corner, center)
            projected_point = self._project_world_point(world_point, context)
            if projected_point is None:
                return None
            projected.append(projected_point)
        return QPolygonF(projected)

    def _plane_center(self) -> Vec3:
        if self.use_axis_distance:
            if self.projector_axis == "y":
                return (
                    self.projector_x,
                    self.projector_y + self.distance_m,
                    self.projector_z,
                )
            return (
                self.projector_x,
                self.projector_y,
                self.projector_z + self.distance_m,
            )
        return (
            self.plane_center_x,
            self.plane_center_y,
            self.plane_center_z,
        )

    def _field_center(self) -> Vec3:
        return (self.field_center_x, self.field_center_y, self.field_center_z)

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
        look_target = self._look_target()
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

    def _draw_oriented_box(
        self,
        painter: QPainter,
        context: CameraContext,
        origin: Vec3,
        look_target: Vec3,
        box_color: QColor,
        direction_color: QColor,
        label: str,
    ) -> None:
        w = self.projector_width
        h = self.projector_height
        d = self.projector_depth
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

        def local_to_world(lx: float, ly: float, lz: float) -> Vec3:
            return (
                origin[0] + right[0] * lx + up[0] * ly + forward[0] * lz,
                origin[1] + right[1] * lx + up[1] * ly + forward[1] * lz,
                origin[2] + right[2] * lx + up[2] * ly + forward[2] * lz,
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
        forward_line = (
            origin,
            local_to_world(0.0, 0.0, d * 1.25),
        )

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
        dir_pen = QPen(direction_color, 2)

        painter.setPen(box_pen)
        for i0, i1 in edges:
            projected_segment = self._project_segment_clipped(
                corners[i0], corners[i1], context
            )
            if projected_segment is None:
                continue
            pa, pb = projected_segment
            painter.drawLine(pa, pb)

        projected_forward = self._project_segment_clipped(
            forward_line[0], forward_line[1], context
        )
        if projected_forward is not None:
            painter.setPen(dir_pen)
            pa, pb = projected_forward
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

    def _draw_device_boxes(
        self, painter: QPainter, viewport_width: int, viewport_height: int
    ) -> None:
        context = self._camera_projection_context(viewport_width, viewport_height)
        if context is None:
            return

        w = self.projector_width
        h = self.projector_height
        d = self.projector_depth
        if w <= 0 or h <= 0 or d <= 0:
            return

        projector_origin: Vec3 = (
            self.projector_x,
            self.projector_y,
            self.projector_z,
        )
        surface_camera_origin: Vec3 = (
            self.main_camera_x,
            self.main_camera_y,
            self.main_camera_z,
        )
        look_target = self._look_target()
        self._draw_oriented_box(
            painter,
            context,
            projector_origin,
            look_target,
            QColor(255, 146, 56),
            QColor(255, 214, 120),
            "Projector",
        )
        self._draw_oriented_box(
            painter,
            context,
            surface_camera_origin,
            look_target,
            QColor(56, 180, 255),
            QColor(104, 240, 255),
            "Surface Camera",
        )
