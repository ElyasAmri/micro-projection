"""calibration.py — Tilt-flip / inverse-grating calibration from a flat reference.

Lifts the calibration step out of notebook cells 8-11 into two reusable
functions: a 2D tilt-plane fit and the tilt-flip inverse-phase computation
(Ch.4 §4.3.1, Eq. 4-2 through Eq. 4-7).

Architectural constraints
-------------------------
- No Geometry argument on any function. The whole point of Ch.4 §4.3.1 is
  that calibration absorbs the system parameters (theta, a, M, lambda_eq)
  empirically. Reaching for them would defeat the trick's purpose.
- Pure NumPy. No scipy, no skimage.

Note on 1D vs 2D tilt fit
-------------------------
Notebook cell 9 fits a 1D line to the row-mean profile and tiles it back
to 2D — i.e., it assumes a pure-x tilt. This module instead fits a true
2D plane P(x, y) = m_x*x + m_y*y + c via lstsq, per the Task 2.4 spec.
The two approaches produce numerically equivalent results when the input
phi is y-invariant (the operational case for the notebook's analytical
flat reference); the 2D fit also handles a small real-world rotation
around the optical axis if one shows up later in calibration.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np


def fit_tilt_plane(
    phi_flat: np.ndarray,
) -> Tuple[np.ndarray, Tuple[float, float, float]]:
    """Least-squares fit of a 2D tilt plane to a flat-reference phase map.

    Solves

        min_{m_x, m_y, c}  || m_x*x + m_y*y + c - phi_flat(x, y) ||_2

    via np.linalg.lstsq on the design matrix [x_flat, y_flat, 1_flat].

    Parameters
    ----------
    phi_flat : ndarray, shape (H, W)
        Measured unwrapped phase on the flat calibration surface, in
        radians. Typically the notebook's `phi1_unwrapped`.

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
