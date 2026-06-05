"""io_utils.py — I/O helpers for frames, calibration files, results.

Houses (Stage 6 B.4):
- ``ShowcaseConfig`` — the complete, reloadable parameter set that reproduces a
  B.3a beyond-Nyquist steep-dome showcase run, serialized to **JSON**
  (scalars/params; human-readable + diffable). This is the foundation for the
  B.4 reference artifact the Stage 7 hardware phase validates against.

Still planned (stub):
- np.savez_compressed wrappers for captured PSI stacks / the B.4 array +
  headline-number reference (B.4 commit 2 — ARRAYS go in .npz, not JSON).
- PNG read/write for projector patterns.

Layering note: this module is GUI-AGNOSTIC by design — it owns the config
*schema*, not the showcase *values*. Callers that know the live B.3a defaults
(the test suite, the artifact generator) bind them in; core never imports the
GUI. Keep it that way so the hardware phase can reuse this serializer.

lambda_eq is DERIVED from the geometry inputs (M, p, theta_projector,
theta_camera) and is therefore NOT serialized — ``to_geometry()`` recomputes it
on load, so a saved config can never carry a stale/inconsistent lambda_eq. The
deliberate empirical override (``HybridGeometry.lambda_eq_override``) is rejected
at capture time (see ``from_geometry``); pinning it would be a conscious future
schema addition, not a silent passthrough.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Union

from geometry import HybridGeometry

# Bump when the serialized schema changes incompatibly. Cheap insurance for an
# artifact the hardware phase validates against — a future loader can branch on
# this rather than mis-reading an old file's fields.
CONFIG_SCHEMA_VERSION: int = 1

PathLike = Union[str, Path]


@dataclass(frozen=True)
class ShowcaseConfig:
    """Full reproducing parameter set for a B.3a steep-dome showcase run.

    Captures everything that determines the run's output (see Stage 6 B.4
    recon item 1): the steep-dome golden, grid, demo defect, geometry inputs,
    PSI step count, sensor-noise sigma/seed, and the three mode flags.

    Geometry is stored as its INPUT fields only (``geometry_M``, ``geometry_p``,
    ``geometry_a``, ``theta_projector_rad``, ``theta_camera_rad``) — exactly the
    five fields ``_build_geometry`` sets. lambda_eq is recomputed from them via
    ``to_geometry``; the derived value is never serialized. The vestigial
    ``HybridGeometry`` fields ``H``/``W``/``pixel_pitch_um`` are deliberately
    excluded: the showcase uses their defaults and the math reads the array
    shape from ``surface_shape``, not from them.
    """

    # Surface (steep-dome golden). amplitude_px / sigma_px are make_steep_dome's
    # defaults (math-pixel convention), captured explicitly so the reference is
    # self-contained.
    surface_amplitude_px: float
    surface_sigma_px: float
    # Grid.
    surface_shape: tuple[int, int]
    pixel_size_mm: float
    # Demo defect (pixel/lambda_eq convention for the steep dome).
    defect_amplitude_px: float
    defect_sigma_px: float
    # Geometry INPUT fields (radians for the angles); lambda_eq recomputed on load.
    geometry_M: float
    geometry_p: float
    geometry_a: float
    theta_projector_rad: float
    theta_camera_rad: float
    # Phase-shifting.
    n_psi_steps: int
    # Sensor noise.
    noise_sigma: float
    noise_seed: int
    # Mode flags (B.3a headline = inverse on, defect on, noise on).
    inverse_fpp_on: bool
    inject_defect_on: bool
    noise_on: bool
    # Schema version — last so callers needn't pass it.
    schema_version: int = CONFIG_SCHEMA_VERSION

    # ------------------------------------------------------------------
    # Capture (geometry -> config), with the lambda_eq-override guard.
    # ------------------------------------------------------------------
    @classmethod
    def from_geometry(
        cls,
        geometry: HybridGeometry,
        *,
        surface_amplitude_px: float,
        surface_sigma_px: float,
        surface_shape: tuple[int, int],
        pixel_size_mm: float,
        defect_amplitude_px: float,
        defect_sigma_px: float,
        n_psi_steps: int,
        noise_sigma: float,
        noise_seed: int,
        inverse_fpp_on: bool,
        inject_defect_on: bool,
        noise_on: bool,
    ) -> "ShowcaseConfig":
        """Build a config from a live ``HybridGeometry`` + the scalar params.

        Guard: the geometry must be on the ANALYTICAL path
        (``lambda_eq_override is None``). We serialize the geometry inputs and
        recompute lambda_eq on load; silently dropping a deliberate empirical
        override would desync the reloaded value from what produced the run.
        """
        if geometry.lambda_eq_override is not None:
            raise ValueError(
                "ShowcaseConfig captures the analytical-geometry path: "
                "lambda_eq_override must be None (inputs are serialized and "
                "lambda_eq is recomputed on load). Pinning an empirical "
                "override is a deliberate future schema addition, not a "
                "silent passthrough."
            )
        return cls(
            surface_amplitude_px=surface_amplitude_px,
            surface_sigma_px=surface_sigma_px,
            surface_shape=tuple(surface_shape),
            pixel_size_mm=pixel_size_mm,
            defect_amplitude_px=defect_amplitude_px,
            defect_sigma_px=defect_sigma_px,
            geometry_M=geometry.M,
            geometry_p=geometry.p,
            geometry_a=geometry.a,
            theta_projector_rad=geometry.theta_projector,
            theta_camera_rad=geometry.theta_camera,
            n_psi_steps=n_psi_steps,
            noise_sigma=noise_sigma,
            noise_seed=noise_seed,
            inverse_fpp_on=inverse_fpp_on,
            inject_defect_on=inject_defect_on,
            noise_on=noise_on,
        )

    # ------------------------------------------------------------------
    # Reconstruct geometry (lambda_eq recomputed from the serialized inputs).
    # ------------------------------------------------------------------
    def to_geometry(self) -> HybridGeometry:
        """Rebuild the ``HybridGeometry`` from the serialized inputs.

        lambda_eq is recomputed by ``equivalent_wavelength()`` — it is never
        read from the file, so it cannot be stale. Mirrors ``_build_geometry``
        (H/W/pixel_pitch_um left at their defaults — math-irrelevant here).
        """
        return HybridGeometry(
            M=self.geometry_M,
            p=self.geometry_p,
            a=self.geometry_a,
            theta_projector=self.theta_projector_rad,
            theta_camera=self.theta_camera_rad,
        )

    # ------------------------------------------------------------------
    # Dict <-> config (JSON has no tuple: surface_shape list<->tuple).
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["surface_shape"] = list(self.surface_shape)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ShowcaseConfig":
        d = dict(d)
        d["surface_shape"] = tuple(d["surface_shape"])
        return cls(**d)


def save_config(config: ShowcaseConfig, path: PathLike) -> None:
    """Write a ``ShowcaseConfig`` to ``path`` as pretty, key-sorted JSON
    (deterministic + diffable)."""
    text = json.dumps(config.to_dict(), indent=2, sort_keys=True)
    Path(path).write_text(text + "\n", encoding="utf-8")


def load_config(path: PathLike) -> ShowcaseConfig:
    """Load a ``ShowcaseConfig`` from a JSON file written by ``save_config``."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ShowcaseConfig.from_dict(data)
