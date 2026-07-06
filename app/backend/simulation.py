"""Simulation-backed "virtual rig": stands in for the projector + camera by
rendering the capture stack with Blender.

- projection is in-process numpy (the shared `fringe_pattern`); the simulation
  has no physical projector, so `project()` stays a no-op.
- `capture` renders an N-step phase sequence with Blender out-of-process
  (`BlenderCapture`, driving `simulation/capture_pipeline.py` in a QProcess).
- `reconstruct` is the shared, sim-provided maths (see `Backend.reconstruct`),
  scored against the specimen's exact ground truth.

Everything not specific to Blender lives in `Backend`; this module is just the
simulation's answers to "what specimens?" and "how do I render a capture?".
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from backend.base import Backend, out_root, repo_root, sim_dir
from backend.capture import CaptureController
from ui.process_runner import ProcessRunner


@dataclass
class CaptureSpec:
    """How to render a capture stack: the argv to run (Blender), the working
    directory, where frames will land, and how many there will be."""

    argv: list[str]
    cwd: Path
    capture_dir: Path
    n_steps: int


# A fine roughness texture (surfaces.rough) needs a dense surface mesh to carry
# its sub-mm displacement -- otherwise the camera images an aliased mesh, not the
# roughness. Smooth mm-scale specimens don't: capture_pipeline's default grid is
# plenty for them. Keyed by surface name; anything not listed renders at the
# default density.
FINE_MESH_SUBDIVISIONS = 1000
_FINE_MESH_SURFACES = {"rough"}


class SimulationBackend(Backend):
    """Drives the fringe-projection loop against the simulation instead of
    hardware."""

    kind = "sim"
    kind_label = "Simulation"

    # -- specimens -----------------------------------------------------------

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
        for root in (out_root() / "surface_tests", out_root() / "app"):
            if not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                capture = child / "capture"
                if capture.is_dir() and any(capture.glob("frame_*.png")):
                    names.add(child.name)
        return sorted(names)

    # -- capture (delegates to Blender via capture_pipeline.py) --------------

    def new_capture_controller(self, parent=None) -> "BlenderCapture":
        return BlenderCapture(self, parent)

    def capture_command(
        self,
        surface: str,
        n_steps: int = 8,
        n_periods: float | None = None,
        samples: int = 64,
        subdir: str = "capture",
        subdivisions: int | None = None,
    ) -> CaptureSpec:
        """Describe how to render `surface`'s frames with Blender (an argv the
        UI runs in a QProcess). Frames land in out/app/<surface>/<subdir>.

        `subdivisions` overrides the surface mesh density; left None, it's chosen
        per surface (fine for roughness specimens, capture_pipeline's default
        otherwise)."""
        n = self.n_periods if n_periods is None else n_periods
        if subdivisions is None and surface in _FINE_MESH_SURFACES:
            subdivisions = FINE_MESH_SUBDIVISIONS
        script = sim_dir() / "capture_pipeline.py"
        if not script.is_file():
            raise FileNotFoundError(f"capture_pipeline.py not found at {script} (set MP_SIMULATION_DIR)")
        capture_dir = out_root() / "app" / surface / subdir
        argv = [
            self.blender_path(), "-b", "-P", str(script), "--",
            "--surface", surface,
            "--out-dir", str(capture_dir),
            "--n-steps", str(n_steps),
            "--n-periods", str(n),
            "--samples", str(samples),
        ]
        if subdivisions:
            argv += ["--subdivisions", str(subdivisions)]
        return CaptureSpec(argv=argv, cwd=repo_root(), capture_dir=capture_dir, n_steps=n_steps)

    # -- rig preview (annotated Blender overview of the scene geometry) ------

    def rig_preview_path(self) -> Path:
        """Where the annotated rig overview render lands (and is loaded from)."""
        return out_root() / "rig_model" / "overview_annotated.png"

    def rig_preview_command(
        self,
        samples: int = 32,
        azimuth: float | None = None,
        elevation: float | None = None,
        distance: float | None = None,
    ) -> CaptureSpec:
        """Describe how to render the rig overview (simulation/rig_preview.py)
        with Blender: one annotated frame showing the projector, the camera,
        and the surface. `azimuth`/`elevation` (degrees) and `distance` (m)
        orbit the viewpoint around the scene; left None, the script's default
        framing is used. `--python-exit-code` makes a script failure a nonzero
        exit instead of Blender's default success."""
        script = sim_dir() / "rig_preview.py"
        if not script.is_file():
            raise FileNotFoundError(f"rig_preview.py not found at {script} (set MP_SIMULATION_DIR)")
        out = self.rig_preview_path()
        argv = [
            self.blender_path(), "-b", "--python-exit-code", "1", "-P", str(script), "--",
            "--out", str(out),
            "--samples", str(samples),
        ]
        for flag, value in (("--azimuth", azimuth), ("--elevation", elevation),
                            ("--distance", distance)):
            if value is not None:
                argv += [flag, f"{float(value):g}"]
        return CaptureSpec(argv=argv, cwd=repo_root(), capture_dir=out.parent, n_steps=1)

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


class BlenderCapture(CaptureController):
    """Async capture that renders the stack with Blender. Wraps a `ProcessRunner`
    (a QProcess), translating start(surface, n_steps, ...) into the Blender argv
    via the backend's `capture_command`, and forwarding its output/terminal
    signals to the shared `CaptureController` interface."""

    def __init__(self, backend: SimulationBackend, parent=None) -> None:
        super().__init__(parent)
        self._backend = backend
        self._runner = ProcessRunner(self)
        self._runner.line.connect(self.line)
        self._runner.finished.connect(self.finished)
        self._runner.failed.connect(self.failed)

    def is_running(self) -> bool:
        return self._runner.is_running()

    def start(self, *, surface: str, n_steps: int, subdir: str,
              n_periods: float | None = None, **kwargs) -> None:
        if self._runner.is_running():
            raise RuntimeError("a capture is already running")
        samples = int(kwargs["samples"]) if "samples" in kwargs else 64
        subdivisions = int(kwargs["subdivisions"]) if "subdivisions" in kwargs else None
        spec = self._backend.capture_command(
            surface, n_steps=n_steps, n_periods=n_periods, samples=samples,
            subdir=subdir, subdivisions=subdivisions,
        )
        self.capture_dir = spec.capture_dir
        self.n_steps = spec.n_steps
        self._runner.start(spec.argv, str(spec.cwd))
