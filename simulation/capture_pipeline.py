"""8-step phase-shifting acquisition: project N phase-shifted fringe patterns
onto the surface and capture each with the telecentric camera.

Builds the same rig as rig_setup.py (see simulation/rig.py), then steps the
projector's phase_fraction node through N evenly-spaced values (each a fraction
of one cycle), rendering the telecentric camera's view at each step. This is
the *acquisition* stage only -- phase extraction / unwrapping / height
reconstruction from this frame stack is a separate step (see reconstruct.py).

Run:
    blender -b -P simulation/capture_pipeline.py -- --out-dir out/capture --n-steps 8 --samples 64
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rig  # noqa: E402
import surfaces  # noqa: E402


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="out/capture")
    parser.add_argument("--n-steps", type=int, default=8)
    parser.add_argument("--n-periods", type=float, default=8.0)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--surface", default="bump", choices=sorted(surfaces.SURFACES))
    parser.add_argument("--subdivisions", type=int, default=rig.SURFACE_GRID_SUBDIVISIONS,
                        help="surface mesh grid density; raise it for fine roughness (surfaces.rough)")
    parser.add_argument("--z-offset", type=float, default=0.0,
                        help="raise the whole surface by this many mm (a simulated z-stage, for calibration)")
    parser.add_argument("--target-dots", action="store_true",
                        help="render a single dot-grid target frame (for lateral pixel->world calibration) instead of a fringe stack")
    parser.add_argument("--dot-spacing", type=float, default=8.0, help="dot grid spacing (mm)")
    parser.add_argument("--dot-radius", type=float, default=1.2, help="dot radius (mm)")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.target_dots:
        rig.clear_scene()
        cam = rig.add_telecentric_camera()
        rig.add_target_plane(spacing_mm=args.dot_spacing, radius_mm=args.dot_radius)
        rig.render(bpy.context.scene, cam, rig.CAM_PIXELS, out_dir / "target.png", args.samples)
        print(f"[capture_pipeline] target (dot spacing {args.dot_spacing}mm) -> {out_dir / 'target.png'}")
        return

    rig.clear_scene()
    projector = rig.add_projector()
    height_fn = surfaces.SURFACES[args.surface]
    _, phase_fraction = rig.add_surface(projector, n_periods=args.n_periods, height_fn=height_fn,
                                        subdivisions=args.subdivisions, z_offset_mm=args.z_offset)
    cam = rig.add_telecentric_camera()

    scene = bpy.context.scene
    for n in range(args.n_steps):
        # n/N steps through exactly one cycle in N evenly-spaced increments,
        # matching delta_n = 2*pi*n/N in the N-step PSA (see report/math.tex).
        phase_fraction.outputs[0].default_value = n / args.n_steps
        rig.render(scene, cam, rig.CAM_PIXELS, out_dir / f"frame_{n:02d}.png", args.samples)
        print(f"[capture_pipeline] frame {n + 1}/{args.n_steps} done")

    print(f"Captured {args.n_steps} phase-shifted frames of '{args.surface}' to {out_dir}")


if __name__ == "__main__":
    main()
