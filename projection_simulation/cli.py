import argparse


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open a projection window for an image or generated fringe."
    )
    parser.add_argument(
        "image",
        nargs="?",
        help="Image file to display when --source image is used.",
    )
    parser.add_argument(
        "--source",
        choices=["fringe", "image"],
        default="fringe",
        help="Projection source. Default: fringe.",
    )
    parser.add_argument(
        "--screen",
        type=int,
        default=0,
        help="Target screen index. Default: 0.",
    )
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="Use fullscreen projector mode.",
    )
    parser.add_argument(
        "--window-width",
        type=int,
        default=1280,
        help="Window width when not fullscreen. Default: 1280.",
    )
    parser.add_argument(
        "--window-height",
        type=int,
        default=720,
        help="Window height when not fullscreen. Default: 720.",
    )
    parser.add_argument(
        "--mode",
        choices=["fit", "plane3d"],
        default="plane3d",
        help="Projection mode: fit or 3D plane projection. Default: plane3d.",
    )
    parser.add_argument(
        "--fill",
        action="store_true",
        help="Fill output area in fit mode (may crop).",
    )
    parser.add_argument(
        "--no-force-landscape",
        action="store_true",
        help="Do not rotate portrait images to horizontal orientation.",
    )
    parser.add_argument(
        "--mirror-horizontal",
        action="store_true",
        help="Mirror image horizontally.",
    )
    parser.add_argument(
        "--fov-deg",
        type=float,
        default=59.4,
        help="User-view camera vertical FOV in degrees for 3D mode. Default: 59.4.",
    )
    parser.add_argument(
        "--projector-fov-deg",
        type=float,
        default=None,
        help=(
            "Projector vertical FOV in degrees. "
            "If omitted, it is auto-fitted to active projection surfaces."
        ),
    )
    parser.add_argument(
        "--distance-m",
        type=float,
        default=15.0,
        help="Projector-to-plane distance in 3D world units (assumed cm). Default: 15.",
    )
    parser.add_argument(
        "--use-axis-distance",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Place the plane using --projector-axis + --distance-m from projector "
            "instead of explicit plane center coordinates."
        ),
    )
    parser.add_argument(
        "--projector-x",
        type=float,
        default=-23.03598,
        help="Projector X position in world units (Unity Y-up converted).",
    )
    parser.add_argument(
        "--projector-y",
        type=float,
        default=-16.110981,
        help="Projector Y/depth in world units (converted from Unity Z).",
    )
    parser.add_argument(
        "--projector-z",
        type=float,
        default=5.0,
        help="Projector Z/height in world units (converted from Unity Y).",
    )
    parser.add_argument(
        "--main-camera-x",
        type=float,
        default=23.035976,
        help="Main Camera X position in world units (Unity Y-up converted).",
    )
    parser.add_argument(
        "--main-camera-y",
        type=float,
        default=-16.110981,
        help="Main Camera Y/depth in world units (converted from Unity Z).",
    )
    parser.add_argument(
        "--main-camera-z",
        type=float,
        default=5.0,
        help="Main Camera Z/height in world units (converted from Unity Y).",
    )
    parser.add_argument(
        "--projector-axis",
        choices=["y", "z"],
        default="y",
        help="Projector forward axis for axis-distance placement. Default: y.",
    )
    parser.add_argument(
        "--plane-center-x",
        type=float,
        default=0.0,
        help="Projection plane center X in world units. Default from Unity sample.",
    )
    parser.add_argument(
        "--plane-center-y",
        type=float,
        default=10.005,
        help="Projection plane center Y/depth in world units (converted from Unity Z).",
    )
    parser.add_argument(
        "--plane-center-z",
        type=float,
        default=5.0,
        help="Projection plane center Z/height in world units (converted from Unity Y).",
    )
    parser.add_argument(
        "--plane-width-m",
        type=float,
        default=20.0,
        help="Physical plane width in world units (cm) for 3D mode. Default: 20.",
    )
    parser.add_argument(
        "--plane-height-m",
        type=float,
        default=10.0,
        help="Physical plane height in world units (cm) for 3D mode. Default: 10.0.",
    )
    parser.add_argument(
        "--project-projection-plane",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Show the 'Projection Plane' surface as a solid color (no projection texture).",
    )
    parser.add_argument(
        "--project-field-object",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Project onto the field object surface from Unity sample.",
    )
    parser.add_argument(
        "--field-center-x",
        type=float,
        default=0.0,
        help="Field object center X in world units (Unity 'Cube').",
    )
    parser.add_argument(
        "--field-center-y",
        type=float,
        default=10.0,
        help="Field object center Y/depth in world units (converted from Unity Z).",
    )
    parser.add_argument(
        "--field-center-z",
        type=float,
        default=5.0,
        help="Field object center Z/height in world units (converted from Unity Y).",
    )
    parser.add_argument(
        "--field-width-m",
        type=float,
        default=6.0,
        help="Field object width in world units. Default: 6.0.",
    )
    parser.add_argument(
        "--field-height-m",
        type=float,
        default=3.0,
        help="Field object height in world units. Default: 3.0.",
    )
    parser.add_argument(
        "--camera-x",
        type=float,
        default=11.380266,
        help="Camera X position in 3D world units. Default from Unity sample.",
    )
    parser.add_argument(
        "--camera-y",
        type=float,
        default=-7.300273,
        help="Camera Y/depth in 3D world units (converted from Unity Z).",
    )
    parser.add_argument(
        "--camera-z",
        type=float,
        default=8.280639,
        help="Camera Z/height in 3D world units (converted from Unity Y).",
    )
    parser.add_argument(
        "--ground-grid",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Show Blender-like ground grid in 3D mode (default: enabled).",
    )
    parser.add_argument(
        "--grid-step",
        type=float,
        default=1.0,
        help="Grid spacing in world units. Default: 1.0.",
    )
    parser.add_argument(
        "--grid-extent",
        type=float,
        default=25.0,
        help="Grid half-extent in world units. Default: 25.0.",
    )
    parser.add_argument(
        "--grid-major-every",
        type=int,
        default=5,
        help="Use a major line every N grid lines. Default: 5.",
    )
    parser.add_argument(
        "--projector-box",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Show projector and surface-camera wireframe boxes in 3D mode.",
    )
    parser.add_argument(
        "--projector-width",
        type=float,
        default=5.5,
        help="Wireframe box width in world units (cm). Default: 5.5.",
    )
    parser.add_argument(
        "--projector-height",
        type=float,
        default=5.5,
        help="Wireframe box height in world units (cm). Default: 5.5.",
    )
    parser.add_argument(
        "--projector-depth",
        type=float,
        default=5.5,
        help="Wireframe box depth in forward-axis units (cm). Default: 5.5.",
    )
    parser.add_argument(
        "--projector-lens-offset-x",
        type=float,
        default=1.0,
        help="Projector lens offset along local right axis from chassis center (cm). Default: 1.0.",
    )
    parser.add_argument(
        "--projector-lens-offset-y",
        type=float,
        default=2.0,
        help="Projector lens offset along local up axis from chassis center (cm). Default: 2.0.",
    )
    parser.add_argument(
        "--projector-lens-offset-z",
        type=float,
        default=0.0,
        help="Projector lens offset along local forward axis from chassis center (cm).",
    )
    parser.add_argument(
        "--yaw-deg",
        type=float,
        default=0.0,
        help="Yaw angle in degrees (left/right). Default: 0.",
    )
    parser.add_argument(
        "--pitch-deg",
        type=float,
        default=0.0,
        help="Pitch angle in degrees (up/down tilt). Default: 0.",
    )
    parser.add_argument(
        "--roll-deg",
        type=float,
        default=0.0,
        help="Roll angle in degrees. Default: 0.",
    )
    parser.add_argument(
        "--fringe-width",
        type=int,
        default=1920,
        help="Generated fringe width in pixels. Default: 1920.",
    )
    parser.add_argument(
        "--fringe-height",
        type=int,
        default=1080,
        help="Generated fringe height in pixels. Default: 1080.",
    )
    parser.add_argument(
        "--fringe-period-px",
        type=float,
        default=48.0,
        help="Fringe period in pixels. Default: 48.",
    )
    parser.add_argument(
        "--fringe-phase-deg",
        type=float,
        default=0.0,
        help="Fringe phase in degrees. Default: 0.",
    )
    parser.add_argument(
        "--fringe-orientation",
        choices=["vertical", "horizontal"],
        default="vertical",
        help="Fringe orientation. Default: vertical.",
    )
    parser.add_argument(
        "--fringe-contrast",
        type=float,
        default=1.0,
        help="Fringe contrast in [0,1]. Default: 1.0.",
    )
    parser.add_argument(
        "--fringe-bias",
        type=float,
        default=0.5,
        help="Fringe brightness bias in [0,1]. Default: 0.5.",
    )
    return parser.parse_args(argv)
