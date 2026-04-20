import argparse
import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import QApplication

from .cli import parse_args
from .fringe import generate_fringe_image
from .types import Vec3
from .window import ProjectionWindow


def _resolve_plane_center(args: argparse.Namespace) -> Vec3:
    if args.use_axis_distance:
        return (
            (args.projector_x, args.projector_y + args.distance_m, args.projector_z)
            if args.projector_axis == "y"
            else (args.projector_x, args.projector_y, args.projector_z + args.distance_m)
        )
    return (args.plane_center_x, args.plane_center_y, args.plane_center_z)


def _resolve_look_target(args: argparse.Namespace) -> Vec3:
    plane_center = _resolve_plane_center(args)
    field_center = (args.field_center_x, args.field_center_y, args.field_center_z)
    look_targets: list[Vec3] = []
    if args.project_projection_plane:
        look_targets.append(plane_center)
    if args.project_field_object:
        look_targets.append(field_center)
    return (
        sum(c[0] for c in look_targets) / len(look_targets),
        sum(c[1] for c in look_targets) / len(look_targets),
        sum(c[2] for c in look_targets) / len(look_targets),
    )


def _validate_args(args: argparse.Namespace) -> str | None:
    if args.mode != "plane3d":
        return None
    if not (1.0 < args.fov_deg < 179.0):
        return "--fov-deg must be between 1 and 179."
    if args.projector_fov_deg is not None and not (1.0 < args.projector_fov_deg < 179.0):
        return "--projector-fov-deg must be between 1 and 179."
    if args.use_axis_distance and args.distance_m <= 0:
        return "--distance-m must be > 0."
    if args.plane_width_m <= 0:
        return "--plane-width-m must be > 0."
    if args.plane_height_m <= 0:
        return "--plane-height-m must be > 0."
    if args.field_width_m <= 0:
        return "--field-width-m must be > 0."
    if args.field_height_m <= 0:
        return "--field-height-m must be > 0."
    if not args.project_projection_plane and not args.project_field_object:
        return "Enable at least one of --project-projection-plane or --project-field-object."
    if args.grid_step <= 0:
        return "--grid-step must be > 0."
    if args.grid_extent <= 0:
        return "--grid-extent must be > 0."
    if args.grid_major_every <= 0:
        return "--grid-major-every must be > 0."
    if args.projector_width <= 0:
        return "--projector-width must be > 0."
    if args.projector_height <= 0:
        return "--projector-height must be > 0."
    if args.projector_depth <= 0:
        return "--projector-depth must be > 0."

    look_target = _resolve_look_target(args)
    if (
        args.camera_x == look_target[0]
        and args.camera_y == look_target[1]
        and args.camera_z == look_target[2]
    ):
        return "Camera position must not coincide with look target."
    return None


def _load_source_image(args: argparse.Namespace) -> QImage:
    if args.source == "image":
        if not args.image:
            raise ValueError("Image path is required when --source image is used.")
        image_path = Path(args.image)
        if not image_path.exists():
            raise ValueError(f"Image not found: {image_path}")
        image = QImage(str(image_path))
        if image.isNull():
            raise ValueError(f"Failed to read image: {image_path}")
        return image

    return generate_fringe_image(
        args.fringe_width,
        args.fringe_height,
        period_px=args.fringe_period_px,
        phase_deg=args.fringe_phase_deg,
        orientation=args.fringe_orientation,
        contrast=args.fringe_contrast,
        bias=args.fringe_bias,
    )


def main() -> int:
    args = parse_args()

    try:
        image = _load_source_image(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    error = _validate_args(args)
    if error is not None:
        print(error, file=sys.stderr)
        return 1

    app = QApplication(sys.argv)
    screens = QGuiApplication.screens()
    if not screens:
        print("No screens detected.", file=sys.stderr)
        return 1
    if args.screen < 0 or args.screen >= len(screens):
        print(
            f"Invalid screen index {args.screen}. Available: 0..{len(screens) - 1}",
            file=sys.stderr,
        )
        return 1

    target_screen = screens[args.screen]
    window = ProjectionWindow(
        image,
        mode=args.mode,
        fill=args.fill,
        fullscreen=args.fullscreen,
        force_landscape=not args.no_force_landscape,
        mirror_horizontal=args.mirror_horizontal,
        fov_deg=args.fov_deg,
        projector_fov_deg=args.projector_fov_deg,
        distance_m=args.distance_m,
        use_axis_distance=args.use_axis_distance,
        projector_x=args.projector_x,
        projector_y=args.projector_y,
        projector_z=args.projector_z,
        main_camera_x=args.main_camera_x,
        main_camera_y=args.main_camera_y,
        main_camera_z=args.main_camera_z,
        plane_center_x=args.plane_center_x,
        plane_center_y=args.plane_center_y,
        plane_center_z=args.plane_center_z,
        plane_width_m=args.plane_width_m,
        plane_height_m=args.plane_height_m,
        project_projection_plane=args.project_projection_plane,
        project_field_object=args.project_field_object,
        field_center_x=args.field_center_x,
        field_center_y=args.field_center_y,
        field_center_z=args.field_center_z,
        field_width_m=args.field_width_m,
        field_height_m=args.field_height_m,
        projector_axis=args.projector_axis,
        camera_x=args.camera_x,
        camera_y=args.camera_y,
        camera_z=args.camera_z,
        show_ground_grid=args.ground_grid,
        grid_step=args.grid_step,
        grid_extent=args.grid_extent,
        grid_major_every=args.grid_major_every,
        show_projector=args.projector_box,
        projector_width=args.projector_width,
        projector_height=args.projector_height,
        projector_depth=args.projector_depth,
        projector_lens_offset_x=args.projector_lens_offset_x,
        projector_lens_offset_y=args.projector_lens_offset_y,
        projector_lens_offset_z=args.projector_lens_offset_z,
        yaw_deg=args.yaw_deg,
        pitch_deg=args.pitch_deg,
        roll_deg=args.roll_deg,
    )
    if window.windowHandle() is not None:
        window.windowHandle().setScreen(target_screen)
    if args.fullscreen:
        window.setGeometry(target_screen.geometry())
        window.showFullScreen()
    else:
        available = target_screen.availableGeometry()
        width = max(320, min(args.window_width, available.width()))
        height = max(240, min(args.window_height, available.height()))
        x = available.x() + (available.width() - width) // 2
        y = available.y() + (available.height() - height) // 2
        window.setGeometry(x, y, width, height)
        window.show()

    print(
        f"Projection window open in {args.mode} mode (source: {args.source}). "
        "Use left-drag to orbit, mouse wheel to zoom, sliders for projector angle/plane distance/FOV, and Esc/Q to close."
    )
    return app.exec()
