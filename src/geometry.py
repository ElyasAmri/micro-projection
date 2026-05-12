"""geometry.py — Geometry abstractions for the fringe projection system.

Defines a `Geometry` Protocol and two concrete implementations:
- `HybridGeometry` (operational default): telecentric camera + non-telecentric
  projector, matching the actual lab hardware.
- `SymmetricGeometry` (NON-OPERATIONAL): textbook symmetric configuration kept
  for cross-validation against the thesis equations and for reproducing the
  current notebook's recovery (which uses the symmetric form).

Magnification convention
------------------------
The **modern** convention M = (sensor size) / (object size) is used throughout
(M = 0.09 for the Edmund Optics #58-259 telecentric lens). The Samara thesis
uses the inverse convention (M_chapter = 1 / M_modern ~ 11.1 for our lens).
Conversion happens at equation boundaries inside this module.

Default geometry — why hybrid
-----------------------------
- Camera arm: Edmund Optics #58-259 telecentric, <0.2 degrees telecentricity.
  Contributes essentially zero perspective bias.
- Projector arm: non-telecentric. Pico Genie Impact 2.0 today; future
  projector unknown. ALL measurable perspective bias originates here.

The system is therefore hybrid; `HybridGeometry` is the operational class.
If the upgraded projector turns out to be telecentric, the inverse-grating
correction collapses gracefully to a uniform pattern and HybridGeometry
remains valid (the bias term simply vanishes).

`SymmetricGeometry` matches what the existing notebook uses (M = 1, both arms
treated with a single `theta` and the Eq. 4-11 sin form). It does NOT model
the lab hardware and should be used only for thesis cross-checks and for
comparing module outputs against the regression fixture.

Units
-----
- Lengths internal to the simulation: **pixels** (matches the notebook's
  parameter values; e.g., p = 40 pixels, a = 2000 pixels). Pixel pitch is
  exposed so callers can convert to physical units (µm) when needed.
- Angles: radians.
- Phase: radians.

Key chapter equations
---------------------
- Eq. 2-51: general non-telecentric lambda_eq, proportional to
  M*p / (tan theta_camera + tan theta_projector). For the hybrid case
  (theta_camera -> 0) this reduces to M*p / (2*pi * tan theta_projector).
- Eq. 4-11/4-12: symmetric form lambda_eq = M*p / (4*pi * sin theta).
  Implemented only in `SymmetricGeometry`.
- Per Ch.4 §4.3.1, the system parameters need not be measured precisely —
  empirical step-height calibration gives lambda_eq directly. Both classes
  expose a `lambda_eq_override` field that bypasses the analytical formula
  when set, supporting the calibration-file path.

The 2*pi factor explained
-------------------------
The hybrid formula is documented in PROJECT_CONTEXT.md §12 (Decision 3) as
"M*p / tan(theta_projector)". The implementation here includes an explicit
2*pi factor in the denominator: `lambda_eq = M*p / (2*pi * tan theta_p)`.
The 2*pi appears because the project's convention puts phase in **radians**
(so the height-to-phase coefficient K has units rad/length); dropping it
would conflict with the notebook's symmetric form which uses 4*pi*sin(theta).
The symmetric and hybrid coefficients are consistent: in the limit of small
theta and theta_camera -> 0, 4*pi*sin(theta) -> 4*pi*theta and
2*pi*tan(theta) -> 2*pi*theta — i.e., the symmetric one is roughly twice the
hybrid one because the symmetric system has two non-telecentric arms.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Tuple

import numpy as np


class Geometry(Protocol):
    """Abstract geometry interface (PROJECT_CONTEXT.md §7.1).

    All concrete geometries expose:
    - equivalent_wavelength() -> float
    - height_to_phase(h) -> ndarray
    - phase_to_height(psi) -> ndarray
    - projected_pattern(p, phase_shift, shape) -> ndarray
    - forward_intensity(h, p, phase_shift) -> ndarray   [Stage 2 Task 4]

    Phase values are in radians. Length values are in pixels unless a
    method docstring says otherwise.
    """

    def equivalent_wavelength(self) -> float: ...
    def height_to_phase(self, h: np.ndarray) -> np.ndarray: ...
    def phase_to_height(self, psi: np.ndarray) -> np.ndarray: ...
    def projected_pattern(
        self, p: float, phase_shift: float, shape: Tuple[int, int]
    ) -> np.ndarray: ...
    def forward_intensity(
        self, h: np.ndarray, p: float, phase_shift: float
    ) -> np.ndarray: ...


def _sinusoidal_pattern(
    p: float, phase_shift: float, shape: Tuple[int, int]
) -> np.ndarray:
    """Base sinusoidal pattern shared by both geometries.

    Returns 0.5 * (1 + cos(2*pi * x / p + phase_shift)) tiled to `shape`.
    The inverse-grating distortion that compensates for the non-telecentric
    projector bias is applied separately in `pattern_generator.py`.

    Parameters
    ----------
    p : float
        Fringe period in pixels.
    phase_shift : float
        Phase shift in radians.
    shape : (H, W)
        Output array shape.

    Returns
    -------
    ndarray of shape (H, W), dtype float64, values in [0, 1].
    """
    H, W = shape
    x = np.arange(W, dtype=np.float64)
    line = 0.5 * (1.0 + np.cos(2.0 * np.pi * x / p + phase_shift))
    return np.tile(line, (H, 1))


@dataclass
class HybridGeometry:
    """Telecentric camera + non-telecentric projector — OPERATIONAL DEFAULT.

    Camera arm
    ----------
    Telecentric (Edmund Optics #58-259, <0.2 degrees). Contributes zero
    perspective bias by construction. No camera-side theta is needed.

    Projector arm
    -------------
    Non-telecentric. Perspective bias parameterized by:
    - `theta_projector` — projection angle (radians).
    - `a` — internal projector "perspective distance" parameter (pixels).

    Both attributes are placeholders pending hardware measurement; grep for
    "PLACEHOLDER" in this file to locate them. Per Ch.4 §4.3.1, neither
    needs to be measured precisely — empirical step-height calibration via
    `lambda_eq_override` bypasses the analytical formula entirely.

    Equivalent wavelength
    ---------------------
    Default formula: lambda_eq = M*p / (2*pi * tan(theta_projector))
    (Eq. 2-51 reduced for theta_camera -> 0). See the module docstring for
    a note on the 2*pi factor.

    If `lambda_eq_override` is set, the analytical formula is bypassed and
    the override is returned directly. This is the Ch.4 §4.3.1 path.
    """

    # Modern magnification convention. Edmund Optics #58-259 = 0.09x.
    M: float = 0.09
    # Fringe period (pixels). Matches notebook's p1.
    p: float = 40.0
    # PLACEHOLDER: pending hardware measurement. Projection angle (radians).
    theta_projector: float = float(np.deg2rad(15.0))
    # PLACEHOLDER: pending hardware measurement. Internal projector "perspective
    # distance" parameter (pixels). Only used by the forward-model project().
    a: float = 2000.0
    # Default simulation grid; tests can override via constructor.
    H: int = 480
    W: int = 640
    # Pixel pitch on the test surface (µm). From PROJECT_CONTEXT.md §2:
    # camera pitch 4.8 µm / M = 0.09 -> ~53 µm/pixel on the surface.
    pixel_pitch_um: float = 53.0
    # Optional empirical lambda_eq (pixels). When set, equivalent_wavelength()
    # returns this instead of computing from M, p, theta. Ch.4 §4.3.1.
    lambda_eq_override: Optional[float] = None

    def equivalent_wavelength(self) -> float:
        """Equivalent wavelength lambda_eq for the hybrid system.

        Returns
        -------
        float
            lambda_eq = (M * p) / (2 * pi * tan(theta_projector))
            (Eq. 2-51 with theta_camera -> 0), in pixels of height per
            radian of phase. If `lambda_eq_override` is set, that value is
            returned instead (Ch.4 §4.3.1 calibration path).
        """
        if self.lambda_eq_override is not None:
            return float(self.lambda_eq_override)
        return self.M * self.p / (2.0 * np.pi * np.tan(self.theta_projector))

    def height_to_phase(self, h: np.ndarray) -> np.ndarray:
        """Height map (pixels) -> phase contribution (rad).

        Inverse of `phase_to_height`. See Eq. 2-46 / 2-47.

        Parameters
        ----------
        h : ndarray, shape (H, W)
            Height map in pixel units.

        Returns
        -------
        ndarray, shape (H, W), dtype float64
            psi = h / lambda_eq.
        """
        return np.asarray(h, dtype=np.float64) / self.equivalent_wavelength()

    def phase_to_height(self, psi: np.ndarray) -> np.ndarray:
        """Phase (rad) -> height (pixels).

        See Eq. 2-46 / 2-47 (and Eq. 2-57 for the inverse-grating case).

        Parameters
        ----------
        psi : ndarray, shape (H, W)
            Phase in radians (typically the height-induced component after
            carrier and tilt have been removed).

        Returns
        -------
        ndarray, shape (H, W), dtype float64
            h = psi * lambda_eq.
        """
        return np.asarray(psi, dtype=np.float64) * self.equivalent_wavelength()

    def projected_pattern(
        self, p: float, phase_shift: float, shape: Tuple[int, int]
    ) -> np.ndarray:
        """Base sinusoidal projector pattern (no inverse-grating distortion).

        Parameters
        ----------
        p : float
            Fringe period in pixels.
        phase_shift : float
            Phase shift in radians.
        shape : (H, W)
            Output array shape.

        Returns
        -------
        ndarray, shape (H, W), dtype float64, values in [0, 1].
        """
        return _sinusoidal_pattern(p, phase_shift, shape)

    def forward_intensity(
        self, h: np.ndarray, p: float, phase_shift: float
    ) -> np.ndarray:
        """Forward intensity model — implemented in synthetic_fringes.py (Stage 2 Task 4).

        Will compose `synthetic_fringes.project()` (the Taylor-approximation
        projector-bias model from notebook cell 2) with the carrier and
        `height_to_phase(h)` and return A + B*cos(phi + phase_shift).
        """
        raise NotImplementedError(
            "HybridGeometry.forward_intensity is implemented in "
            "synthetic_fringes.py (Stage 2 Task 4)."
        )


@dataclass
class SymmetricGeometry:
    """Symmetric telecentric geometry — NON-OPERATIONAL textbook reference.

    Both camera and projector arms are treated symmetrically with a single
    `theta`. This is the configuration the Samara thesis derives most
    equations under, and it does NOT match the actual lab hardware (which
    is hybrid — see `HybridGeometry`).

    Kept only for:
    - Cross-validation against thesis Eq. 4-11 / 4-12.
    - Reproducing the current notebook's recovery (the notebook uses the
      symmetric form), which is what the Stage 2 regression fixture
      captures. Subsequent module tests that compare against the regression
      fixture should construct a `SymmetricGeometry` with notebook
      parameters (M=1, p=40, theta=15 degrees, 480x640).

    Do not use this class for any decision affecting the lab hardware.
    """

    # Defaults match the current notebook parameter values so the regression
    # fixture is reproduced bit-for-bit by downstream modules.
    M: float = 1.0
    p: float = 40.0
    theta: float = float(np.deg2rad(15.0))
    # Internal projector "perspective distance" parameter (pixels), needed by
    # `synthetic_fringes.project()`. In a symmetric system both arms share
    # this same `a`. Default matches notebook cell 1.
    a: float = 2000.0
    H: int = 480
    W: int = 640
    pixel_pitch_um: float = 53.0
    lambda_eq_override: Optional[float] = None

    @property
    def theta_projector(self) -> float:
        """Alias for `theta` so the bias-parameter contract used by
        `synthetic_fringes.project()` is uniform across geometries.

        In a symmetric system both arms share the same angle, so
        `theta_projector == theta`. The `project()` forward model reads
        `geometry.theta_projector` uniformly; this alias lets a
        `SymmetricGeometry` satisfy that contract without renaming the
        primary `theta` field (which the symmetric `equivalent_wavelength`
        formula still references as `theta`).
        """
        return self.theta

    def equivalent_wavelength(self) -> float:
        """Equivalent wavelength lambda_eq for the symmetric telecentric case.

        Returns
        -------
        float
            lambda_eq = (M * p) / (4 * pi * sin(theta))  per Eq. 4-11.
            If `lambda_eq_override` is set, returns that value instead.
        """
        if self.lambda_eq_override is not None:
            return float(self.lambda_eq_override)
        return self.M * self.p / (4.0 * np.pi * np.sin(self.theta))

    def height_to_phase(self, h: np.ndarray) -> np.ndarray:
        """Height (pixels) -> phase (rad). Inverse of `phase_to_height`."""
        return np.asarray(h, dtype=np.float64) / self.equivalent_wavelength()

    def phase_to_height(self, psi: np.ndarray) -> np.ndarray:
        """Phase (rad) -> height (pixels) via lambda_eq. Eq. 2-46 / 2-47."""
        return np.asarray(psi, dtype=np.float64) * self.equivalent_wavelength()

    def projected_pattern(
        self, p: float, phase_shift: float, shape: Tuple[int, int]
    ) -> np.ndarray:
        """Base sinusoidal pattern. See `HybridGeometry.projected_pattern`."""
        return _sinusoidal_pattern(p, phase_shift, shape)

    def forward_intensity(
        self, h: np.ndarray, p: float, phase_shift: float
    ) -> np.ndarray:
        """Forward intensity model — implemented in synthetic_fringes.py (Stage 2 Task 4)."""
        raise NotImplementedError(
            "SymmetricGeometry.forward_intensity is implemented in "
            "synthetic_fringes.py (Stage 2 Task 4)."
        )
