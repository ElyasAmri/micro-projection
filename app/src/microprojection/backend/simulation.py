"""Simulation-backed "virtual rig": stands in for the projector + camera until
the real hardware is available.

- `generate_fringe()` computes the pattern the projector would emit, in-process
  with numpy (no Blender) -- the Projected Image.
- `reconstruct()` runs the simulation's own `reconstruct.run()` on an existing
  capture stack (the sibling `simulation/` package, imported lazily) -- the
  Reconstructed Surface, scored against that specimen's ground truth.

The Blender-rendered capture (the middle step) is added next; this slice proves
the project + reconstruct ends of the loop without needing Blender. The
simulation is located by path (env `MP_SIMULATION_DIR`, else the sibling
`simulation/`), never imported at app startup.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# app/src/microprojection/backend/simulation.py -> parents[4] == repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]


def _sim_dir() -> Path:
    return Path(os.environ.get("MP_SIMULATION_DIR") or _REPO_ROOT / "simulation")


def _out_root() -> Path:
    return Path(os.environ.get("MP_OUT_DIR") or _REPO_ROOT / "out")


@dataclass
class ReconstructionResult:
    """What a reconstruction produced: the scored metrics and the image files
    the simulation wrote (height map, ground truth, error)."""

    surface: str
    metrics: dict
    height_png: Path
    ground_truth_png: Path
    error_png: Path


class SimulationBackend:
    """Drives the fringe-projection loop against the simulation instead of
    hardware."""

    def __init__(self, n_periods: float = 8.0) -> None:
        self.n_periods = n_periods
        self._sim_reconstruct = None  # imported lazily on first reconstruct()

    # -- projection (in-process, no Blender) ---------------------------------

    def generate_fringe(
        self,
        n_periods: float | None = None,
        phase: float = 0.0,
        width: int = 1140,
        height: int = 912,
    ) -> np.ndarray:
        """The 8-bit grayscale fringe the projector would emit: a vertical
        sinusoid matching the simulation's projected pattern,
        0.5 + 0.5*sin(2*pi*n_periods*u + 2*pi*phase), u across the width."""
        n = self.n_periods if n_periods is None else n_periods
        u = (np.arange(width) + 0.5) / width
        row = 0.5 + 0.5 * np.sin(2.0 * np.pi * n * u + 2.0 * np.pi * phase)
        image = np.broadcast_to(row, (height, width))
        return (image * 255.0).astype(np.uint8)

    # -- specimens that already have a capture stack -------------------------

    def available_surfaces(self) -> list[str]:
        """Specimens with a capture stack ready to reconstruct (no sim import
        needed -- just what's on disk under out/surface_tests)."""
        root = _out_root() / "surface_tests"
        if not root.is_dir():
            return []
        names = []
        for child in sorted(root.iterdir()):
            capture = child / "capture"
            if capture.is_dir() and any(capture.glob("frame_*.png")):
                names.append(child.name)
        return names

    def capture_dir(self, surface: str) -> Path:
        return _out_root() / "surface_tests" / surface / "capture"

    # -- reconstruction (delegates to the simulation) ------------------------

    def reconstruct(self, surface: str, n_periods: float | None = None) -> ReconstructionResult:
        """Run the simulation's reconstruct.run() on `surface`'s capture stack
        and return its outputs (height-map PNG + metrics)."""
        n = self.n_periods if n_periods is None else n_periods
        capture = self.capture_dir(surface)
        if not capture.is_dir() or not any(capture.glob("frame_*.png")):
            raise FileNotFoundError(f"no capture stack for '{surface}' at {capture}")
        sim = self._load_sim_reconstruct()
        out_dir = _out_root() / "app" / surface
        metrics = sim.run(capture, out_dir, n_periods=n, surface=surface, verbose=False)
        return ReconstructionResult(
            surface=surface,
            metrics=metrics,
            height_png=out_dir / "height_reconstructed.png",
            ground_truth_png=out_dir / "height_ground_truth.png",
            error_png=out_dir / "height_error.png",
        )

    def _load_sim_reconstruct(self):
        """Import the simulation's reconstruct module on first use."""
        if self._sim_reconstruct is None:
            sim_dir = str(_sim_dir())
            if not Path(sim_dir).is_dir():
                raise FileNotFoundError(f"simulation not found at {sim_dir} (set MP_SIMULATION_DIR)")
            if sim_dir not in sys.path:
                sys.path.insert(0, sim_dir)
            import reconstruct as sim_reconstruct  # noqa: E402  (sibling sim package)

            self._sim_reconstruct = sim_reconstruct
        return self._sim_reconstruct
