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
- Eq. 2-51 (operational): general two-angle lambda_eq
      lambda_eq = M * p / (2*pi * (tan theta_projector + tan theta_camera))
  Used by BOTH `HybridGeometry` and `SymmetricGeometry`. This is the
  paper's general non-telecentric form; arm angles are independent inputs.
- Eq. 2-52 (sanity check): symmetric special case theta_proj = theta_cam,
  collapses Eq. 2-51 to M*p / (4*pi * tan theta).
- Eq. 4-11 (superseded): symmetric sin-form lambda_eq = M*p / (4*pi*sin theta).
  Used by the original notebook (cell 14) and the prior SymmetricGeometry
  implementation. Replaced in Stage 3.5 by the Eq. 2-51 / 2-52 tan form.
- Per Ch.4 §4.3.1, the system parameters need not be measured precisely —
  empirical step-height calibration gives lambda_eq directly. Both classes
  expose a `lambda_eq_override` field that bypasses the analytical formula
  when set, supporting the calibration-file path.

Two-angle formula — Stage 3.5 (supersedes Stage 2 Decision 3)
-------------------------------------------------------------
The prior single-angle hybrid form `M*p / (2*pi * tan theta_projector)`
implicitly assumed theta_camera = 0 by conflating "telecentric camera lens"
with "camera body mounted vertical." Telecentric only locks the lens
magnification (M is constant regardless of object distance); the camera
body's tilt angle is an independent mechanical parameter. The general
two-angle form (Eq. 2-51) takes both angles as inputs. See
CONVERSATION_SUMMARY.md Sec 7b for the discovery trail.

Degenerate case
---------------
When tan(theta_projector) + tan(theta_camera) == 0 (both arms vertical, or
equal-and-opposite tilts looking at the surface from the same direction),
triangulation has no angular separation and lambda_eq is undefined. The
implementation returns float('inf'); downstream callers (e.g., the Stage 4
GUI) check with `math.isinf(lambda_eq)` and surface the "no height
sensitivity" condition. No exception is raised — IEEE float semantics carry
the meaning cleanly without try/except scaffolding.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Object-space scale bridge (Stage 6 A.0.1) — LABELING ONLY.
#
# These three constants convert pixel counts to physical microns for HUMAN
# DISPLAY (e.g. "the ~2-pixel sampling wall sits at ~107 µm object-space").
# They MUST NOT be read by any math path — not the carrier, not lambda_eq,
# not synthetic_fringes.project(), not synthesize_psi_stack(). The simulation
# core is sealed in pixel-space (p, M, a, the carrier, X=arange(W) are all
# pixel-unit); these constants are an additive labeling layer on top.
#
# CAMERA_MAGNIFICATION is the real imaging magnification (0.09× modern
# convention, Edmund Optics #58-259). It is deliberately kept SEPARATE from
# the geometries' `M` field: the operational pipeline runs M=1.0 in sealed
# pixel-space (see main_window.GEOMETRY_M), so the real 0.09× lives only here
# as a display fact and is NOT cross-wired into lambda_eq.
# ---------------------------------------------------------------------------
CAMERA_PIXEL_PITCH_UM: float = 4.8
CAMERA_MAGNIFICATION: float = 0.09
OBJECT_SPACE_UM_PER_PIXEL: float = CAMERA_PIXEL_PITCH_UM / CAMERA_MAGNIFICATION


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
    Telecentric lens (Edmund Optics #58-259, <0.2 degrees). The telecentric
    lens locks M independent of object distance, so the camera contributes
    essentially zero **lens-side** perspective bias. The camera body's
    **tilt angle** (`theta_camera`) is an independent mechanical parameter
    and enters the triangulation geometry — see CONVERSATION_SUMMARY.md
    Sec 7b for the discovery trail.

    Projector arm
    -------------
    Non-telecentric. Perspective bias parameterized by:
    - `theta_projector` — projection angle (radians).
    - `a` — internal projector "perspective distance" parameter (pixels).

    Both attributes are placeholders pending hardware measurement; grep for
    "PLACEHOLDER" in this file to locate them. Per Ch.4 §4.3.1, neither
    needs to be measured precisely for the inverse-grating correction —
    empirical step-height calibration via `lambda_eq_override` bypasses
    the analytical formula entirely.

    Equivalent wavelength (Eq. 2-51, Stage 3.5)
    -------------------------------------------
    lambda_eq = M * p / (2*pi * (tan(theta_projector) + tan(theta_camera)))

    This is the two-angle general form. Supersedes Stage 2 Decision 3's
    one-angle form `M*p / (2*pi * tan(theta_projector))`, which implicitly
    assumed theta_camera = 0 (a hidden assumption from conflating
    "telecentric lens" with "vertical mount"). See module docstring.

    If `lambda_eq_override` is set, the analytical formula is bypassed and
    the override is returned directly. This is the Ch.4 §4.3.1 path.

    Default for `theta_camera` is `theta_projector` (symmetric default),
    which preserves the prior fixture's effective behavior at the wiring
    level. Pass an explicit value to model an asymmetric mount.
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
    # Camera arm tilt angle (radians). Independent of lens telecentricity.
    # Sentinel `None` means "copy theta_projector at construction time" —
    # the symmetric default. Set explicitly to model an asymmetric mount.
    theta_camera: Optional[float] = None
    # Default simulation grid; tests can override via constructor.
    H: int = 480
    W: int = 640
    # Pixel pitch on the test surface (µm). LABELING-ONLY display value,
    # sourced from the single canonical scale-bridge constant so the number
    # cannot drift (Stage 6 A.0.1). Read by nothing in the math path.
    pixel_pitch_um: float = OBJECT_SPACE_UM_PER_PIXEL
    # Optional empirical lambda_eq (pixels). When set, equivalent_wavelength()
    # returns this instead of computing from M, p, theta. Ch.4 §4.3.1.
    lambda_eq_override: Optional[float] = None

    def __post_init__(self) -> None:
        if self.theta_camera is None:
            self.theta_camera = self.theta_projector

    def equivalent_wavelength(self) -> float:
        """Equivalent wavelength lambda_eq for the hybrid system (Eq. 2-51).

        Returns
        -------
        float
            lambda_eq = M * p / (2*pi * (tan(theta_projector) + tan(theta_camera))),
            in pixels of height per radian of phase. If
            `lambda_eq_override` is set, that value is returned instead
            (Ch.4 §4.3.1 calibration path).

            When tan(theta_projector) + tan(theta_camera) == 0 (both arms
            vertical, or equal-and-opposite tilts), returns float('inf').
            Downstream callers should check with math.isinf(); see module
            docstring "Degenerate case" section.
        """
        if self.lambda_eq_override is not None:
            return float(self.lambda_eq_override)
        denom = 2.0 * np.pi * (np.tan(self.theta_projector) + np.tan(self.theta_camera))
        if denom == 0.0:
            return float("inf")
        return self.M * self.p / denom

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
    primary tilt `theta`. This is the configuration the Samara thesis
    derives most equations under, and it does NOT match the actual lab
    hardware (which is hybrid — see `HybridGeometry`).

    Kept only for:
    - Cross-validation against thesis Eq. 2-52 (symmetric special case of
      Eq. 2-51).
    - Reproducing the current notebook's recovery, which is what the
      Stage 2 regression fixture captures. Subsequent module tests that
      compare against the regression fixture should construct a
      `SymmetricGeometry` with notebook parameters (M=1, p=40,
      theta=15 degrees, 480x640).

    Do not use this class for any decision affecting the lab hardware.

    Equivalent wavelength (Eq. 2-51, Stage 3.5)
    -------------------------------------------
    lambda_eq = M * p / (2*pi * (tan(theta_projector) + tan(theta_camera)))

    This is identical to `HybridGeometry.equivalent_wavelength()` — the
    only difference between the two classes lies in their default M
    (and the conceptual labeling of which arm carries which property).

    Stage 3.5 replaced the previous Eq. 4-11 sin form
    `M*p / (4*pi*sin(theta))` with the Eq. 2-51 tan form. At
    theta_camera = theta_projector this collapses to Eq. 2-52's
    `M*p / (4*pi*tan(theta))`, which is the canonical symmetric form
    (NOT the Eq. 4-11 sin form the notebook used). See module docstring.
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
    # Camera arm tilt (radians). Sentinel `None` means "copy `theta` at
    # construction time" — preserves the symmetric default. Setting this
    # explicitly turns SymmetricGeometry into a non-symmetric configuration
    # at the equivalent_wavelength() level (everything else still uses
    # `theta` as the single shared angle).
    theta_camera: Optional[float] = None
    H: int = 480
    W: int = 640
    # LABELING-ONLY display value, sourced from the canonical scale-bridge
    # constant (Stage 6 A.0.1). Read by nothing in the math path.
    pixel_pitch_um: float = OBJECT_SPACE_UM_PER_PIXEL
    lambda_eq_override: Optional[float] = None

    def __post_init__(self) -> None:
        if self.theta_camera is None:
            self.theta_camera = self.theta

    @property
    def theta_projector(self) -> float:
        """Alias for `theta` so the bias-parameter contract used by
        `synthetic_fringes.project()` is uniform across geometries.

        In a symmetric system both arms share the same projector-facing
        angle, so `theta_projector == theta`. The `project()` forward
        model reads `geometry.theta_projector` uniformly; this alias lets
        a `SymmetricGeometry` satisfy that contract without renaming the
        primary `theta` field.
        """
        return self.theta

    def equivalent_wavelength(self) -> float:
        """Equivalent wavelength lambda_eq (Eq. 2-51).

        Returns
        -------
        float
            lambda_eq = M * p / (2*pi * (tan(theta_projector) + tan(theta_camera))),
            identical to `HybridGeometry.equivalent_wavelength()`. If
            `lambda_eq_override` is set, returns that value instead.

            When tan(theta_projector) + tan(theta_camera) == 0, returns
            float('inf'). See module docstring "Degenerate case".
        """
        if self.lambda_eq_override is not None:
            return float(self.lambda_eq_override)
        denom = 2.0 * np.pi * (np.tan(self.theta_projector) + np.tan(self.theta_camera))
        if denom == 0.0:
            return float("inf")
        return self.M * self.p / denom

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
