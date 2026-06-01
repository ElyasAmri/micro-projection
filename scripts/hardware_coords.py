"""CLI: print camera + projector lens-center world coordinates.

Stage 5 sub-task 4d.11. Thin wrapper over `arm_lens_front_world` — the
same pure helper the GUI "Hardware Coordinates" panel uses, so the CLI
and the GUI report identical numbers for a given pose.

    python scripts/hardware_coords.py
    python scripts/hardware_coords.py --theta-cam 30 --theta-proj 0 --throw 150 --wd 157

Frame: world origin at the stage-surface center, +z up toward the rig
(z=0 = stage). After the 4d.10 anchoring, the projector lens-center
reads (0, 0, ~throw) and the camera (0, 0, WD) when vertical.
"""
from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

from src.gui.hardware_scene import arm_lens_front_world  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print camera + projector lens-center world coordinates (mm)."
    )
    parser.add_argument("--theta-cam", type=float, default=0.0,
                        help="Camera arm tilt, degrees (default 0).")
    parser.add_argument("--theta-proj", type=float, default=0.0,
                        help="Projector arm tilt, degrees (default 0).")
    parser.add_argument("--throw", type=float, default=150.0,
                        help="Projector throw distance, mm (default 150).")
    parser.add_argument("--wd", type=float, default=157.0,
                        help="Camera working distance, mm (default 157).")
    args = parser.parse_args()

    coords = arm_lens_front_world(
        theta_cam_deg=args.theta_cam,
        theta_proj_deg=args.theta_proj,
        proj_dist_mm=args.throw,
        cam_dist_mm=args.wd,
    )
    for name in ("camera", "projector"):
        x, y, z = coords[name]
        print(f"{name:>9}: x={x:+8.2f}  y={y:+8.2f}  z={z:+8.2f} mm")


if __name__ == "__main__":
    main()
