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
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

def _find_repo_root() -> Path:
    """The monorepo root: the nearest ancestor holding both app/ and
    simulation/ (env overrides below make this a soft default)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "app").is_dir() and (parent / "simulation").is_dir():
            return parent
    return here.parents[2]  # app/backend/simulation.py -> repo root


_REPO_ROOT = _find_repo_root()


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


@dataclass
class CaptureSpec:
    """How to render a capture stack: the argv to run (Blender), the working
    directory, where frames will land, and how many there will be. The UI runs
    this in a QProcess so the backend stays Qt-free."""

    argv: list[str]
    cwd: Path
    capture_dir: Path
    n_steps: int


class SimulationBackend:
    """Drives the fringe-projection loop against the simulation instead of
    hardware."""

    def __init__(self, n_periods: float = 8.0) -> None:
        self.n_periods = n_periods
        self._sim_reconstruct = None  # imported lazily on first reconstruct()
        self._sim_surfaces = None  # imported lazily on first surface listing

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
        """Specimens the UI can work with. Prefer the simulation's registry
        (any of these can be captured); fall back to whatever already has
        capture data on disk if the sim isn't importable."""
        try:
            return sorted(self._load_sim_surfaces().SURFACES)
        except Exception:  # noqa: BLE001 - sim missing/unimportable is non-fatal
            return self._surfaces_with_capture_data()

    def _surfaces_with_capture_data(self) -> list[str]:
        names: set[str] = set()
        for root in (_out_root() / "surface_tests", _out_root() / "app"):
            if not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                capture = child / "capture"
                if capture.is_dir() and any(capture.glob("frame_*.png")):
                    names.add(child.name)
        return sorted(names)

    # -- capture (delegates to Blender via capture_pipeline.py) --------------

    def capture_command(
        self,
        surface: str,
        n_steps: int = 8,
        n_periods: float | None = None,
        samples: int = 64,
    ) -> CaptureSpec:
        """Describe how to render `surface`'s phase-shifted capture stack with
        Blender (an argv the UI runs in a QProcess). Frames land in an
        app-owned capture dir so the simulation's own test data is untouched."""
        n = self.n_periods if n_periods is None else n_periods
        script = _sim_dir() / "capture_pipeline.py"
        if not script.is_file():
            raise FileNotFoundError(f"capture_pipeline.py not found at {script} (set MP_SIMULATION_DIR)")
        capture_dir = _out_root() / "app" / surface / "capture"
        argv = [
            self.blender_path(), "-b", "-P", str(script), "--",
            "--surface", surface,
            "--out-dir", str(capture_dir),
            "--n-steps", str(n_steps),
            "--n-periods", str(n),
            "--samples", str(samples),
        ]
        return CaptureSpec(argv=argv, cwd=_REPO_ROOT, capture_dir=capture_dir, n_steps=n_steps)

    def blender_path(self) -> str:
        """Locate the Blender executable (env MP_BLENDER, then PATH, then the
        macOS app bundle)."""
        explicit = os.environ.get("MP_BLENDER")
        if explicit:
            return explicit
        found = shutil.which("blender")
        if found:
            return found
        mac_default = "/Applications/Blender.app/Contents/MacOS/Blender"
        if Path(mac_default).is_file():
            return mac_default
        raise FileNotFoundError("Blender not found (set MP_BLENDER)")

    # -- reconstruction (delegates to the simulation) ------------------------

    def capture_dir(self, surface: str) -> Path:
        """Where reconstruct reads frames: a fresh app-rendered capture if one
        exists, else the simulation's pre-rendered test capture."""
        app_capture = _out_root() / "app" / surface / "capture"
        if app_capture.is_dir() and any(app_capture.glob("frame_*.png")):
            return app_capture
        return _out_root() / "surface_tests" / surface / "capture"

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

    def _ensure_sim_on_path(self) -> None:
        sim_dir = str(_sim_dir())
        if not Path(sim_dir).is_dir():
            raise FileNotFoundError(f"simulation not found at {sim_dir} (set MP_SIMULATION_DIR)")
        if sim_dir not in sys.path:
            sys.path.insert(0, sim_dir)

    def _load_sim_reconstruct(self):
        """Import the simulation's reconstruct module on first use."""
        if self._sim_reconstruct is None:
            self._ensure_sim_on_path()
            import reconstruct as sim_reconstruct  # noqa: E402  (sibling sim package)

            self._sim_reconstruct = sim_reconstruct
        return self._sim_reconstruct

    def _load_sim_surfaces(self):
        """Import the simulation's surfaces registry module on first use."""
        if self._sim_surfaces is None:
            self._ensure_sim_on_path()
            import surfaces as sim_surfaces  # noqa: E402  (sibling sim package)

            self._sim_surfaces = sim_surfaces
        return self._sim_surfaces
