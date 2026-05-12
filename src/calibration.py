"""calibration.py — Tilt-flip / inverse-grating calibration from a flat reference.

Lifts the calibration step out of notebook cells 8-18 into three reusable
functions: a 2D tilt-plane fit, a 1D tilt-line fit, and the tilt-flip
inverse-phase computation (Ch.4 §4.3.1, Eq. 4-2 through Eq. 4-7).

Architectural constraints
-------------------------
- No Geometry argument on any function. The whole point of Ch.4 §4.3.1 is
  that calibration absorbs the system parameters (theta, a, M, lambda_eq)
  empirically. Reaching for them would defeat the trick's purpose.
- Pure NumPy. No scipy, no skimage.

Tilt-fit use-case split
-----------------------
Two tilt fits live here, and they are NOT interchangeable on non-trivial
inputs:

- `fit_tilt_plane` (2D lstsq, [x, y, 1]) — for flat references or any
  measurement where genuine y-tilt may be present (e.g., a small optical-
  axis rotation in the lab). Strict superset of the 1D form when the phase
  is y-invariant. Use for `compute_inverse_phase` (which operates on flat
  references) and any future hardware-calibration code.

- `fit_tilt_line_1d` (1D polyfit on row-mean, tiled) — operational fit for
  object-phase self-calibration per Ch.4 §4.3.1 / notebook cell 18. The
  recovered tilt has m_y == 0 by construction; absorbing the bump into
  m_y is precisely what we DO NOT want, because the height information
  is what we are trying to extract. Use for `recover_object_height`
  when `phi_calibration` is derived from the object phase itself.

The two diverge by ~4e-5 in recovered height on the regression fixture
(Gaussian bump center sits 0.5 px off the grid centroid, so the small
slope bias maps to different coefficient components in the two fits).
That divergence is why `recover_object_height`'s regression test must
match the notebook bit-for-bit by using `fit_tilt_line_1d`, not
`fit_tilt_plane`.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np


def fit_tilt_plane(
    phi_flat: np.ndarray,
) -> Tuple[np.ndarray, Tuple[float, float, float]]:
    """Least-squares fit of a 2D tilt plane to a phase map.

    Solves

        min_{m_x, m_y, c}  || m_x*x + m_y*y + c - phi_flat(x, y) ||_2

    via np.linalg.lstsq on the design matrix [x_flat, y_flat, 1_flat].

    Use-case: flat references, or any measurement where a genuine y-tilt
    may be present (small optical-axis rotation, future hardware
    calibration). On y-invariant data this collapses to the same answer
    as `fit_tilt_line_1d`. On object phase with a centered-but-off-grid
    bump, the two diverge — use `fit_tilt_line_1d` for object self-cal;
    see the module docstring.

    Parameters
    ----------
    phi_flat : ndarray, shape (H, W)
        Measured unwrapped phase, in radians. Typically the notebook's
        `phi1_unwrapped`.

    Returns
    -------
    plane : ndarray, shape (H, W), dtype float64
        The fitted plane evaluated on the same (H, W) integer-pixel grid.
    coeffs : tuple of three floats
        (m_x, m_y, c) — slopes (rad/pixel) and intercept (rad). Exposed
        for diagnostics and downstream use.
    """
    phi = np.asarray(phi_flat, dtype=np.float64)
    if phi.ndim != 2:
        raise ValueError(f"phi_flat must be 2D (H, W); got shape {phi.shape}")
    H, W = phi.shape

    x = np.arange(W, dtype=np.float64)
    y = np.arange(H, dtype=np.float64)
    X, Y = np.meshgrid(x, y)  # both shape (H, W); default 'xy' indexing

    A = np.column_stack(
        [X.ravel(), Y.ravel(), np.ones(H * W, dtype=np.float64)]
    )
    coeffs, _, _, _ = np.linalg.lstsq(A, phi.ravel(), rcond=None)
    m_x, m_y, c = coeffs

    plane = m_x * X + m_y * Y + c
    return plane, (float(m_x), float(m_y), float(c))


def fit_tilt_line_1d(
    phi: np.ndarray,
) -> Tuple[np.ndarray, Tuple[float, float]]:
    """1D tilt fit on the row-mean profile, tiled to (H, W).

    Reproduces notebook cell 18 bit-for-bit:

        profile = phi.mean(axis=0)
        m, c    = np.polyfit(x, profile, 1)
        tilt    = np.tile(m * x + c, (H, 1))

    Use-case: object-phase self-calibration per Ch.4 §4.3.1 / notebook
    cell 18. The recovered tilt has m_y == 0 by construction. This is
    INTENTIONAL for object self-cal: the height bump is what we want to
    extract, not absorb into the fit. A 2D plane fit would let the
    bump's off-centeredness bleed into m_y and contaminate the residual.

    Assumes the residual after tilt removal has zero row-mean — true for
    objects whose height map is roughly centered and small in amplitude
    compared to the carrier, broken for asymmetric or off-center objects.
    For flat-reference calibration or arbitrary tilt patterns, use
    `fit_tilt_plane` instead.

    Parameters
    ----------
    phi : ndarray, shape (H, W)
        Unwrapped phase in radians (typically the object's
        `phi3_unwrapped`).

    Returns
    -------
    plane : ndarray, shape (H, W), dtype float64
        The fitted 1D tilt tiled back to (H, W). Each row is identical.
    coeffs : tuple of two floats
        (m, c) — x-slope (rad/pixel) and intercept (rad). No y-slope is
        returned because none is fit.
    """
    phi_arr = np.asarray(phi, dtype=np.float64)
    if phi_arr.ndim != 2:
        raise ValueError(f"phi must be 2D (H, W); got shape {phi_arr.shape}")
    H, W = phi_arr.shape

    x = np.arange(W, dtype=np.float64)
    profile = phi_arr.mean(axis=0)
    m, c = np.polyfit(x, profile, 1)

    plane = np.tile(m * x + c, (H, 1))
    return plane, (float(m), float(c))


def compute_inverse_phase(phi_flat: np.ndarray) -> np.ndarray:
    """Compute the projector inverse-grating phase phi2 from a flat-reference measurement.

    Implements the tilt-flip trick (Ch.4 §4.3.1, Eq. 4-7):

        phi2(x, y) = 2 * P(x, y) - phi_flat(x, y)

    where P is the best-fit tilt plane through phi_flat (see
    `fit_tilt_plane`). When phi2 is projected through the same biased
    system, the projector bias and the flipped curvature cancel,
    yielding clean fringes on the surface (Eq. 4-9).

    Parameters
    ----------
    phi_flat : ndarray, shape (H, W)
        Measured unwrapped phase on the flat calibration surface, in
        radians.

    Returns
    -------
    ndarray, shape (H, W), dtype float64
        The inverse-grating phase phi2, in radians. Pass this to the
        projector pattern generator to produce the pre-distorted fringes.
    """
    phi = np.asarray(phi_flat, dtype=np.float64)
    plane, _ = fit_tilt_plane(phi)
    return 2.0 * plane - phi
