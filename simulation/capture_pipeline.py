"""8-step phase-shifting acquisition: project N phase-shifted fringe patterns
onto the surface and capture each with the telecentric camera.

Builds the same rig as rig_setup.py (see simulation/rig.py), then steps the
surface's phase_fraction node through N evenly-spaced values (each a fraction
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
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rig.clear_scene()
    projector = rig.add_projector()
    height_fn = surfaces.SURFACES[args.surface]
    _, phase_fraction = rig.add_surface(projector, n_periods=args.n_periods, height_fn=height_fn)
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
