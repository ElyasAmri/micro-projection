"""PRO4500 projector + telecentric camera rig -- single-frame visualization.

Renders an overview shot and the telecentric camera's own view, for visually
verifying the rig geometry derived in report/math.tex. See simulation/rig.py for
the scene-building details and the Blender quirks found while building it.

Run:
    blender -b -P simulation/rig_setup.py -- --out-dir out/rig_model --samples 64
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rig  # noqa: E402


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="out/rig_model")
    parser.add_argument("--samples", type=int, default=64)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rig.clear_scene()
    projector = rig.add_projector()
    rig.add_surface(projector)
    telecentric_cam = rig.add_telecentric_camera()
    overview_cam = rig.add_overview_camera()
    rig.add_marker("ProjectorMarker", projector.location, (0.2, 0.4, 1.0))
    rig.add_marker("CameraMarker", telecentric_cam.location, (1.0, 0.3, 0.2))

    scene = bpy.context.scene
    rig.render(scene, telecentric_cam, rig.CAM_PIXELS, out_dir / "telecentric_view.png", args.samples)
    rig.render(scene, overview_cam, (1600, 900), out_dir / "overview.png", args.samples)

    bpy.ops.wm.save_as_mainfile(filepath=str(out_dir / "rig.blend"))


if __name__ == "__main__":
    main()
