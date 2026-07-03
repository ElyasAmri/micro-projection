"""The backend abstraction the UI talks to -- one interface, two implementations.

`Backend` is the seam between the shell and whatever actually drives the rig:
the `SimulationBackend` (Blender + the numpy reconstruction) or the
`HardwareBackend` (a real projector + camera). The UI only ever calls the
methods declared here, so swapping sim for hardware is a construction choice
(see `backend.factory.create_backend`), not a rewrite.

What differs between backends is *acquisition*: the simulation renders a frame
stack with Blender out-of-process, hardware projects patterns and grabs frames
in-process. Both funnel into the same shape -- a directory of `frame_*.png` --
which the shared, sim-provided reconstruction turns into a height map. So the
projection maths (`fringe_pattern`) and the reconstruction (`reconstruct`) live
here, once, and only the capture step is abstract.

This module stays Qt-free (the `CaptureController` that needs Qt lives in
`backend.capture`) so the reconstruction path can run headless.
"""
from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import numpy as np


# -- repo / output locations (shared by every backend) -----------------------

def _find_repo_root() -> Path:
    """The monorepo root: the nearest ancestor holding both app/ and
    simulation/ (the env overrides below make this a soft default)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "app").is_dir() and (parent / "simulation").is_dir():
            return parent
    return here.parents[2]  # app/backend/base.py -> repo root


_REPO_ROOT = _find_repo_root()


def repo_root() -> Path:
    return _REPO_ROOT


def sim_dir() -> Path:
    return Path(os.environ.get("MP_SIMULATION_DIR") or _REPO_ROOT / "simulation")


def out_root() -> Path:
    return Path(os.environ.get("MP_OUT_DIR") or _REPO_ROOT / "out")


# -- the projected pattern (identical for sim and hardware) ------------------

def fringe_pattern(
    n_periods: float,
    phase: float = 0.0,
    width: int = 1140,
    height: int = 912,
) -> np.ndarray:
    """The 8-bit grayscale fringe the projector emits: a vertical sinusoid,
    0.5 + 0.5*sin(2*pi*n_periods*u + 2*pi*phase), u running across the width.

    The same function feeds the in-app preview, the physical projector, and the
    per-step phase-shift sequence (phase = k/N), so what hardware projects is
    bit-for-bit what the simulation models."""
    u = (np.arange(width) + 0.5) / width
    row = 0.5 + 0.5 * np.sin(2.0 * np.pi * n_periods * u + 2.0 * np.pi * phase)
    image = np.broadcast_to(row, (height, width))
    return (image * 255.0).astype(np.uint8)


@dataclass
class ReconstructionResult:
    """What a reconstruction produced: the scored metrics and the image files
    written (height map always; ground-truth + error only when a known specimen
    gives a ground truth to score against)."""

    surface: str
    metrics: dict
    height_png: Path
    ground_truth_png: Path
    error_png: Path


@dataclass
class NoiseEstimateResult:
    """What a noise estimation produced: the metrics (estimated sigma, and -- in
    a controlled run -- how it compares to the injected level, plus the height
    error margin the reconstruction inherits) and the images written (a
    per-pixel height-uncertainty map and a per-pixel noise map)."""

    surface: str
    metrics: dict
    uncertainty_png: Path
    noise_map_png: Path


class Backend(ABC):
    """The rig, as the UI sees it. Concrete backends fill in how specimens are
    listed, how a capture stack is produced, and (optionally) how a pattern is
    pushed to a physical projector; everything else is shared here."""

    #: short id / human label, surfaced in the sidebar header and logs
    kind: str = "backend"
    kind_label: str = "Backend"

    def __init__(self, n_periods: float = 8.0) -> None:
        self.n_periods = n_periods
        self._sim_reconstruct = None  # imported lazily on first reconstruct()
        self._sim_surfaces = None  # imported lazily on first surface lookup
        self._sim_noise = None  # imported lazily on first estimate_noise()

    # -- projection ----------------------------------------------------------

    def generate_fringe(
        self,
        n_periods: float | None = None,
        phase: float = 0.0,
        width: int = 1140,
        height: int = 912,
    ) -> np.ndarray:
        n = self.n_periods if n_periods is None else n_periods
        return fringe_pattern(n, phase, width, height)

    def project(self, fringe: np.ndarray) -> None:
        """Push a pattern to a *physical* projector, if this backend has one.
        The simulation has none, so this is a no-op there; hardware overrides
        it to display on the projector screen."""

    # -- specimens / capture (backend-specific) ------------------------------

    @abstractmethod
    def available_surfaces(self) -> list[str]:
        """Names the UI can select and capture/reconstruct under."""

    @abstractmethod
    def new_capture_controller(self, parent=None):
        """A fresh `CaptureController` (async project->capture->frames) wired to
        this backend. The UI connects to its line/finished/failed signals and
        calls start(surface=..., n_steps=..., subdir=...)."""

    def capture_dir(self, surface: str) -> Path:
        """Where reconstruct reads frames: a freshly captured app stack if one
        exists, else the simulation's pre-rendered test capture (if any)."""
        app_capture = out_root() / "app" / surface / "capture"
        if app_capture.is_dir() and any(app_capture.glob("frame_*.png")):
            return app_capture
        return out_root() / "surface_tests" / surface / "capture"

    # -- reconstruction (shared: same maths for sim and hardware) ------------

    def reconstruct(self, surface: str, n_periods: float | None = None) -> ReconstructionResult:
        """Run the shared reconstruction on `surface`'s latest capture stack.
        If `surface` is a known simulation specimen its exact ground truth is
        used to score the result (RMSE/R^2, error map); a real-world target
        ('live') has no ground truth, so only the height map is produced."""
        n = self.n_periods if n_periods is None else n_periods
        capture = self.capture_dir(surface)
        if not capture.is_dir() or not any(capture.glob("frame_*.png")):
            raise FileNotFoundError(f"no capture stack for '{surface}' at {capture}")
        sim = self._load_sim_reconstruct()
        out_dir = out_root() / "app" / surface
        gt_surface = surface if self._has_ground_truth(surface) else None
        metrics = sim.run(capture, out_dir, n_periods=n, surface=gt_surface, verbose=False)
        return ReconstructionResult(
            surface=surface,
            metrics=metrics,
            height_png=out_dir / "height_reconstructed.png",
            ground_truth_png=out_dir / "height_ground_truth.png",
            error_png=out_dir / "height_error.png",
        )

    # -- noise estimation (shared) -------------------------------------------

    def estimate_noise(
        self,
        surface: str,
        injected_sigma_dn: float | None = None,
        gain_swing_pct: float = 0.0,
        n_periods: float | None = None,
    ) -> NoiseEstimateResult:
        """Analyze the error a capture stack imposes on the reconstruction:
        random noise and auto-exposure brightness swing.

        For a known specimen, this is the controlled experiment: synthesize a
        stack with a *known* noise level and/or brightness swing, estimate them
        back, and check the predicted noise margin against the actual
        reconstruction error -- reported both without and with exposure
        correction, so the cost of the swing (and how much correcting it
        recovers) is explicit. For a real target it measures the noise and swing
        already in the captured stack (no injected truth, no ground-truth
        reconstruction to compare against)."""
        n = self.n_periods if n_periods is None else n_periods
        sim_noise = self._load_sim_noise()
        known = self._has_ground_truth(surface)
        out_dir = out_root() / "app" / surface

        injected = None
        controlled = known and (injected_sigma_dn or gain_swing_pct)
        if controlled:  # synthesize a stack with the requested imperfections
            stack_dir = out_dir / "noise_stack"
            sim_noise.synth_noisy_stack(
                stack_dir, surface, n_periods=n, n_steps=8,
                sigma=(injected_sigma_dn or 0.0) / 255.0,
                gain_swing=(gain_swing_pct or 0.0) / 100.0,
            )
            injected = injected_sigma_dn / 255.0 if injected_sigma_dn else None
        else:  # estimate what's already in a captured stack
            stack_dir = self.capture_dir(surface)
            if not stack_dir.is_dir() or not any(stack_dir.glob("frame_*.png")):
                raise FileNotFoundError(f"no capture stack for '{surface}' at {stack_dir}")

        metrics = sim_noise.run(
            stack_dir, out_dir, n_periods=n,
            surface=(surface if known else None), injected_sigma=injected, verbose=False,
        )
        # Cross-check against real reconstruction error, without vs with the
        # exposure-swing correction, so the swing's cost is a concrete number.
        if known:
            rec = self._load_sim_reconstruct()
            rec_dir = out_dir / "noise_recon"
            raw = rec.run(stack_dir, rec_dir, n_periods=n, surface=surface,
                          normalize_gains=False, verbose=False)
            corrected = rec.run(stack_dir, rec_dir, n_periods=n, surface=surface,
                                normalize_gains=True, verbose=False)
            metrics["rmse_raw_mm"] = raw.get("rmse")
            metrics["rmse_corrected_mm"] = corrected.get("rmse")
            metrics["actual_rmse_mm"] = corrected.get("rmse")  # the shipped pipeline corrects

        return NoiseEstimateResult(
            surface=surface,
            metrics=metrics,
            uncertainty_png=out_dir / "noise_uncertainty.png",
            noise_map_png=out_dir / "noise_map.png",
        )

    def _has_ground_truth(self, surface: str) -> bool:
        try:
            return surface in self._load_sim_surfaces().SURFACES
        except Exception:  # noqa: BLE001 - sim registry missing => treat as unknown
            return False

    # -- lazy simulation imports (the reconstruction lives in simulation/) ----

    def _ensure_sim_on_path(self) -> None:
        d = str(sim_dir())
        if not Path(d).is_dir():
            raise FileNotFoundError(f"simulation not found at {d} (set MP_SIMULATION_DIR)")
        if d not in sys.path:
            sys.path.insert(0, d)

    def _load_sim_reconstruct(self):
        if self._sim_reconstruct is None:
            self._ensure_sim_on_path()
            import reconstruct as sim_reconstruct  # noqa: E402  (sibling sim package)

            self._sim_reconstruct = sim_reconstruct
        return self._sim_reconstruct

    def _load_sim_surfaces(self):
        if self._sim_surfaces is None:
            self._ensure_sim_on_path()
            import surfaces as sim_surfaces  # noqa: E402  (sibling sim package)

            self._sim_surfaces = sim_surfaces
        return self._sim_surfaces

    def _load_sim_noise(self):
        if self._sim_noise is None:
            self._ensure_sim_on_path()
            import noise_estimate as sim_noise  # noqa: E402  (sibling sim package)

            self._sim_noise = sim_noise
        return self._sim_noise
