import argparse
import importlib
import sys
import time
import traceback
from collections import deque
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import QApplication

from .cli import parse_args
from .fringe import generate_fringe_image
from .types import Vec3
from .window import ProjectionWindow

WATCHED_SUFFIXES = {".py"}
EXCLUDED_DIRS = {".git", ".archive", "__pycache__", ".idea"}


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


def _create_projection_window(args: argparse.Namespace, image: QImage) -> ProjectionWindow:
    return ProjectionWindow(
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


def _apply_args_to_window(window: ProjectionWindow, args: argparse.Namespace) -> None:
    window.mode = args.mode
    window.fill = args.fill
    window.fullscreen = args.fullscreen
    window.force_landscape = not args.no_force_landscape
    window.mirror_horizontal = args.mirror_horizontal
    window.fov_deg = args.fov_deg
    window.projector_fov_deg = args.projector_fov_deg
    window.use_axis_distance = args.use_axis_distance
    window.projector_x = args.projector_x
    window.projector_y = args.projector_y
    window.projector_z = args.projector_z
    window.main_camera_x = args.main_camera_x
    window.main_camera_y = args.main_camera_y
    window.main_camera_z = args.main_camera_z
    window.plane_center_x = args.plane_center_x
    window.plane_center_y = args.plane_center_y
    window.plane_center_z = args.plane_center_z
    window.plane_width_m = args.plane_width_m
    window.plane_height_m = args.plane_height_m
    window.project_projection_plane = args.project_projection_plane
    window.project_field_object = args.project_field_object
    window.field_center_x = args.field_center_x
    window.field_center_y = args.field_center_y
    window.field_center_z = args.field_center_z
    window.field_width_m = args.field_width_m
    window.field_height_m = args.field_height_m
    window.projector_axis = args.projector_axis
    window.camera_x = args.camera_x
    window.camera_y = args.camera_y
    window.camera_z = args.camera_z
    window.show_ground_grid = args.ground_grid
    window.grid_step = args.grid_step
    window.grid_extent = args.grid_extent
    window.grid_major_every = args.grid_major_every
    window.show_projector = args.projector_box
    window.projector_width = args.projector_width
    window.projector_height = args.projector_height
    window.projector_depth = args.projector_depth
    window.projector_lens_offset_x = args.projector_lens_offset_x
    window.projector_lens_offset_y = args.projector_lens_offset_y
    window.projector_lens_offset_z = args.projector_lens_offset_z
    window.yaw_deg = args.yaw_deg
    window.pitch_deg = args.pitch_deg
    window.roll_deg = args.roll_deg

    window._default_projector_fov_deg = window._compute_default_projector_fov_deg()
    window._base_plane_center = window._resolve_base_plane_center(args.distance_m)
    window._symmetry_normal, window._symmetry_tangent = window._derive_symmetry_basis()
    window._projection_angle_deg, window.distance_m = window._derive_initial_projection_geometry(
        args.distance_m
    )
    window._device_distance_m = window.distance_m
    window._base_distance_m = window.distance_m
    window._update_reflected_devices()
    window._plane_shift_direction = (
        -window._symmetry_normal[0],
        -window._symmetry_normal[1],
        -window._symmetry_normal[2],
    )
    window._sync_orbit_from_camera()
    window._refresh_control_labels()
    window._controls_frame.setVisible(window.mode == "plane3d")


def _patch_window_class(window: ProjectionWindow) -> None:
    module_names = (
        "projection_simulation.math3d",
        "projection_simulation.types",
        "projection_simulation.fringe",
        "projection_simulation.window",
    )
    for module_name in module_names:
        module = sys.modules.get(module_name)
        if module is None:
            importlib.import_module(module_name)
            continue
        importlib.reload(module)

    window_module = importlib.import_module("projection_simulation.window")
    refreshed_window_cls = getattr(window_module, "ProjectionWindow")
    current_window_cls = window.__class__
    for name, value in refreshed_window_cls.__dict__.items():
        if name in {"__dict__", "__weakref__"}:
            continue
        setattr(current_window_cls, name, value)

    global ProjectionWindow
    ProjectionWindow = refreshed_window_cls


def _hot_reload_projection_window(window: ProjectionWindow, argv: list[str]) -> None:
    importlib.invalidate_caches()
    _patch_window_class(window)

    cli_module = importlib.import_module("projection_simulation.cli")
    reloaded_parse_args = getattr(cli_module, "parse_args")
    reloaded_args = reloaded_parse_args(argv)

    error = _validate_args(reloaded_args)
    if error is not None:
        raise ValueError(error)

    image = _load_source_image(reloaded_args)
    _apply_args_to_window(window, reloaded_args)
    window._processed = window._process_image(image)
    window.update()


def _collect_snapshot(root: Path) -> dict[Path, tuple[int, int]]:
    snapshot: dict[Path, tuple[int, int]] = {}
    for path in root.rglob("*"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if not path.is_file() or path.suffix.lower() not in WATCHED_SUFFIXES:
            continue
        try:
            stat = path.stat()
        except (FileNotFoundError, PermissionError, OSError):
            continue
        snapshot[path] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def _detect_changes(
    previous: dict[Path, tuple[int, int]],
    current: dict[Path, tuple[int, int]],
) -> list[Path]:
    changed_paths: list[Path] = []
    all_paths = set(previous.keys()) | set(current.keys())
    for path in sorted(all_paths):
        if previous.get(path) != current.get(path):
            changed_paths.append(path)
    return changed_paths


def _guard_reload_rate(reload_times: deque[float]) -> None:
    now = time.monotonic()
    reload_times.append(now)
    while reload_times and now - reload_times[0] > 10.0:
        reload_times.popleft()
    if len(reload_times) >= 6:
        print("[runner] Too many rapid reloads, pausing briefly...")
        time.sleep(2.0)


def _format_change_preview(root: Path, changed: list[Path]) -> str:
    preview = ", ".join(str(p.relative_to(root)) for p in changed[:3])
    suffix = "" if len(changed) <= 3 else ", ..."
    return f"{preview}{suffix}"


def _enable_hot_reload(
    window: ProjectionWindow,
    args_for_reload: list[str],
    interval_seconds: float,
) -> QTimer:
    root = Path(__file__).resolve().parent.parent
    snapshot = _collect_snapshot(root)
    reload_times: deque[float] = deque()

    timer = QTimer(window)
    timer.setInterval(max(120, int(interval_seconds * 1000)))

    def on_timeout() -> None:
        nonlocal snapshot
        current = _collect_snapshot(root)
        changed = _detect_changes(snapshot, current)
        snapshot = current
        if not changed:
            return
        print(f"[runner] Change detected: {_format_change_preview(root, changed)}")
        _guard_reload_rate(reload_times)
        try:
            _hot_reload_projection_window(window, args_for_reload)
            print("[runner] Reloaded window in place.")
        except Exception as exc:
            print(f"[runner] Hot reload failed: {exc}", file=sys.stderr)
            traceback.print_exc()

    timer.timeout.connect(on_timeout)
    timer.start()
    return timer


def main(argv: list[str] | None = None, *, hot_reload_interval: float | None = None) -> int:
    args = parse_args(argv)

    try:
        image = _load_source_image(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    error = _validate_args(args)
    if error is not None:
        print(error, file=sys.stderr)
        return 1

    qt_argv = [sys.argv[0], *(argv or [])] if argv is not None else sys.argv
    app = QApplication.instance()
    if app is None:
        app = QApplication(qt_argv)
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

    if hot_reload_interval is not None:
        args_for_reload = list(argv) if argv is not None else sys.argv[1:]
        window._hot_reload_timer = _enable_hot_reload(window, args_for_reload, hot_reload_interval)
        print("[runner] Debug mode enabled. Hot reloading in place...")

    print(
        f"Projection window open in {args.mode} mode (source: {args.source}). "
        "Use left-drag to orbit, mouse wheel to zoom, sliders for projector angle/plane distance/FOV, and Esc/Q to close."
    )
    return app.exec()
