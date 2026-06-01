"""Stage 5 sub-task 4d.11 — scripts/hardware_coords.py CLI.

Runs the CLI in a subprocess and asserts it prints the same lens-center
world coordinates the shared `arm_lens_front_world` helper returns. This
locks the "single source of truth" contract: the CLI must not drift from
the helper (and therefore from the GUI panel, which uses the same helper).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

from gui.hardware_scene import arm_lens_front_world

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SCRIPT = os.path.join(_ROOT, "scripts", "hardware_coords.py")

_FLOATS = re.compile(r"[-+]?\d+\.\d+")


def _run_cli(theta_cam, theta_proj, throw, wd):
    """Invoke the CLI; return {name: (x, y, z)} parsed from stdout."""
    result = subprocess.run(
        [
            sys.executable, _SCRIPT,
            "--theta-cam", str(theta_cam),
            "--theta-proj", str(theta_proj),
            "--throw", str(throw),
            "--wd", str(wd),
        ],
        capture_output=True, text=True, check=True,
    )
    parsed = {}
    for line in result.stdout.splitlines():
        if ":" not in line:
            continue
        name, _, rest = line.partition(":")
        nums = [float(v) for v in _FLOATS.findall(rest)]
        if len(nums) == 3:
            parsed[name.strip()] = tuple(nums)
    return parsed


def test_cli_matches_helper_when_vertical():
    coords = arm_lens_front_world(
        theta_cam_deg=0.0, theta_proj_deg=0.0,
        proj_dist_mm=150.0, cam_dist_mm=157.0,
    )
    cli = _run_cli(0.0, 0.0, 150.0, 157.0)

    for name in ("camera", "projector"):
        # CLI prints 2 decimals; compare at that precision.
        for cli_v, helper_v in zip(cli[name], coords[name]):
            assert round(helper_v, 2) == cli_v, (
                f"{name}: CLI {cli_v} != helper {round(helper_v, 2)}"
            )


def test_cli_matches_helper_at_tilt():
    coords = arm_lens_front_world(
        theta_cam_deg=15.0, theta_proj_deg=-25.0,
        proj_dist_mm=120.0, cam_dist_mm=170.0,
    )
    cli = _run_cli(15.0, -25.0, 120.0, 170.0)

    for name in ("camera", "projector"):
        for cli_v, helper_v in zip(cli[name], coords[name]):
            assert round(helper_v, 2) == cli_v, (
                f"{name}: CLI {cli_v} != helper {round(helper_v, 2)}"
            )
