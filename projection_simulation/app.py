import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QImage, QSurfaceFormat
from PySide6.QtWidgets import QApplication

from .cli import parse_args
from .fringe import generate_fringe_image
from .types import Vec3
from .window import DEFAULT_DEVICE_SPACING_CM, ProjectionWindow

_Transform = Callable[[object], object]
RELOAD_EXIT_CODE = 75
WINDOW_ARG_BINDINGS: tuple[tuple[str, str, _Transform | None], ...] = (
    ("mode", "mode", None),
    ("fill", "fill", None),
    ("fullscreen", "fullscreen", None),
    ("force_landscape", "no_force_landscape", lambda value: not bool(value)),
    ("mirror_horizontal", "mirror_horizontal", None),
    ("fov_deg", "fov_deg", None),
    ("projector_fov_deg", "projector_fov_deg", None),
    ("use_axis_distance", "use_axis_distance", None),
    ("projector_x", "projector_x", None),
    ("projector_y", "projector_y", None),
    ("projector_z", "projector_z", None),
    ("main_camera_x", "main_camera_x", None),
    ("main_camera_y", "main_camera_y", None),
    ("main_camera_z", "main_camera_z", None),
    ("plane_center_x", "plane_center_x", None),
    ("plane_center_y", "plane_center_y", None),
    ("plane_center_z", "plane_center_z", None),
    ("plane_width_m", "plane_width_m", None),
    ("plane_height_m", "plane_height_m", None),
    ("project_projection_plane", "project_projection_plane", None),
    ("project_field_object", "project_field_object", None),
    ("field_center_x", "field_center_x", None),
    ("field_center_y", "field_center_y", None),
    ("field_center_z", "field_center_z", None),
    ("field_width_m", "field_width_m", None),
    ("field_height_m", "field_height_m", None),
    ("projector_axis", "projector_axis", None),
    ("camera_x", "camera_x", None),
    ("camera_y", "camera_y", None),
    ("camera_z", "camera_z", None),
    ("show_ground_grid", "ground_grid", None),
    ("grid_step", "grid_step", None),
    ("grid_extent", "grid_extent", None),
    ("grid_major_every", "grid_major_every", None),
    ("projector_lens_offset_x", "projector_lens_offset_x", None),
    ("projector_lens_offset_y", "projector_lens_offset_y", None),
    ("projector_lens_offset_z", "projector_lens_offset_z", None),
    ("yaw_deg", "yaw_deg", None),
    ("pitch_deg", "pitch_deg", None),
    ("roll_deg", "roll_deg", None),
)


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


def _window_state_from_args(args: argparse.Namespace) -> dict[str, object]:
    state: dict[str, object] = {}
    for window_attr, arg_attr, transform in WINDOW_ARG_BINDINGS:
        value = getattr(args, arg_attr)
        state[window_attr] = transform(value) if transform is not None else value
    return state


def _create_projection_window(args: argparse.Namespace, image: QImage) -> ProjectionWindow:
    window = ProjectionWindow(image, distance_m=args.distance_m, **_window_state_from_args(args))
    _configure_window_projection_source(window, args)
    return window


def _configure_window_projection_source(
    window: ProjectionWindow, args: argparse.Namespace
) -> None:
    window.configure_projection_source(
        source=args.source,
        fringe_width=args.fringe_width,
        fringe_height=args.fringe_height,
        fringe_period_px=args.fringe_period_px,
        fringe_phase_deg=args.fringe_phase_deg,
        fringe_orientation=args.fringe_orientation,
        fringe_contrast=args.fringe_contrast,
        fringe_bias=args.fringe_bias,
    )


def _apply_args_to_window(window: ProjectionWindow, args: argparse.Namespace) -> None:
    for attr, value in _window_state_from_args(args).items():
        setattr(window, attr, value)
    _configure_window_projection_source(window, args)

    window._default_projector_fov_deg = window._compute_default_projector_fov_deg()
    window._base_plane_center = window._resolve_base_plane_center(args.distance_m)
    window._symmetry_normal, window._symmetry_tangent = window._derive_symmetry_basis()
    window._projection_angle_deg, window.distance_m = window._derive_initial_projection_geometry(
        args.distance_m
    )
    window._device_distance_m = window.distance_m
    window._device_lateral_sign = -1.0 if window._projection_angle_deg < 0.0 else 1.0
    window._device_spacing_cm = DEFAULT_DEVICE_SPACING_CM
    window._base_distance_m = window.distance_m
    window._plane_shift_direction = (
        -window._symmetry_normal[0],
        -window._symmetry_normal[1],
        -window._symmetry_normal[2],
    )
    window._update_reflected_devices()
    window._sync_orbit_from_camera()
    window._refresh_control_labels()
    window._controls_frame.setVisible(window.mode == "plane3d")


def _enable_manual_reload(window: ProjectionWindow) -> None:
    def on_reload() -> None:
        print("[reload-debug] on_reload requested app restart", flush=True)
        app = QApplication.instance()
        if app is None:
            print("[reload-debug] on_reload aborted (no QApplication instance)", flush=True)
            return
        app.setQuitOnLastWindowClosed(False)
        app.closeAllWindows()
        app.processEvents()
        app.exit(RELOAD_EXIT_CODE)

    window.set_reload_handler(on_reload)


def main(argv: list[str] | None = None, *, debug_mode: bool = False) -> int:
    args = parse_args(argv)

    try:
        image = _load_source_image(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1

    error = _validate_args(args)
    if error is not None:
        print(error, file=sys.stderr, flush=True)
        return 1

    qt_argv = [sys.argv[0], *(argv or [])] if argv is not None else sys.argv
    app = QApplication.instance()
    if app is None:
        surface_format = QSurfaceFormat()
        surface_format.setRenderableType(QSurfaceFormat.OpenGL)
        surface_format.setProfile(QSurfaceFormat.CompatibilityProfile)
        surface_format.setVersion(2, 1)
        surface_format.setDepthBufferSize(24)
        surface_format.setSamples(4)
        QSurfaceFormat.setDefaultFormat(surface_format)
        app = QApplication(qt_argv)
    if debug_mode:
        app.aboutToQuit.connect(
            lambda: print("[reload-debug] QApplication.aboutToQuit emitted", flush=True)
        )

    screens = QGuiApplication.screens()
    if not screens:
        print("No screens detected.", file=sys.stderr, flush=True)
        return 1
    if args.screen < 0 or args.screen >= len(screens):
        print(
            f"Invalid screen index {args.screen}. Available: 0..{len(screens) - 1}",
            file=sys.stderr,
            flush=True,
        )
        return 1

    target_screen = screens[args.screen]
    window = _create_projection_window(args, image)
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

    if debug_mode:
        _enable_manual_reload(window)
        print("[runner] Debug mode enabled. Press R (or F5) to restart app.", flush=True)

    print(
        f"Projection window open in {args.mode} mode (source: {args.source}). "
        "Use left-drag to orbit, mouse wheel to zoom, sliders for proj-telecentric spacing/plane distance/FOV, and Esc to close.",
        flush=True,
    )
    exit_code = app.exec()
    if debug_mode:
        print(f"[reload-debug] app.exec returned {exit_code}", flush=True)
    return exit_code
