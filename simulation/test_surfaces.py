"""Validate the reconstruction pipeline against a battery of known test
surfaces (surfaces.SURFACES).

For each surface: renders an 8-frame capture via capture_pipeline.py (run
as a Blender subprocess -- that part needs bpy), then reconstructs height
in-process (reconstruct.py, plain numpy/opencv) and scores it against that
surface's exact ground truth. Prints a summary table.

Run (no Blender import needed directly here -- shells out to it per
surface):
    .venv/bin/python3 simulation/test_surfaces.py \
        --blender /Applications/Blender.app/Contents/MacOS/Blender
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reconstruct  # noqa: E402
import surfaces  # noqa: E402


def find_blender(explicit: str | None) -> str:
    if explicit:
        return explicit
    found = shutil.which("blender")
    if found:
        return found
    mac_default = "/Applications/Blender.app/Contents/MacOS/Blender"
    if Path(mac_default).exists():
        return mac_default
    raise FileNotFoundError("Blender not found on PATH; pass --blender explicitly")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender", default=None)
    parser.add_argument("--out-root", default=Path("out/surface_tests"), type=Path)
    parser.add_argument("--n-steps", type=int, default=8)
    parser.add_argument("--n-periods", type=float, default=8.0)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--surfaces", nargs="*", default=sorted(surfaces.SURFACES), choices=sorted(surfaces.SURFACES))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    blender = find_blender(args.blender)
    repo_root = Path(__file__).resolve().parent.parent
    args.out_root.mkdir(parents=True, exist_ok=True)

    results = []
    for name in args.surfaces:
        capture_dir = args.out_root / name / "capture"
        recon_dir = args.out_root / name / "reconstruction"
        print(f"\n=== {name} ===")
        subprocess.run(
            [
                blender, "-b", "-P", str(repo_root / "simulation" / "capture_pipeline.py"), "--",
                "--surface", name,
                "--out-dir", str(capture_dir),
                "--n-steps", str(args.n_steps),
                "--n-periods", str(args.n_periods),
                "--samples", str(args.samples),
            ],
            check=True,
            cwd=repo_root,
        )
        metrics = reconstruct.run(capture_dir, recon_dir, n_periods=args.n_periods, surface=name)
        results.append(metrics)

    print("\n=== Summary ===")
    header = f"{'surface':<14}{'RMSE(mm)':>10}{'MAE(mm)':>10}{'max|err|':>10}{'R^2':>8}{'valid%':>8}"
    print(header)
    print("-" * len(header))
    for m in results:
        valid_pct = 100.0 * m["valid_pixels"] / m["total_pixels"]
        print(f"{m['surface']:<14}{m['rmse']:>10.4f}{m['mae']:>10.4f}{m['max_abs']:>10.4f}{m['r2']:>8.4f}{valid_pct:>7.1f}%")

    with open(args.out_root / "summary.txt", "w") as f:
        f.write(header + "\n")
        for m in results:
            valid_pct = 100.0 * m["valid_pixels"] / m["total_pixels"]
            f.write(f"{m['surface']:<14}{m['rmse']:>10.4f}{m['mae']:>10.4f}{m['max_abs']:>10.4f}{m['r2']:>8.4f}{valid_pct:>7.1f}%\n")
    print(f"\nwrote {args.out_root / 'summary.txt'}")


if __name__ == "__main__":
    main()
