"""Tests for pattern_generator.inverse_grating_phase (Stage 6 A.1).

The inverse grating is the tilt-flip phi_inverse = 2*P - phi_ref (P = the linear
plane fit). These tests pin:

  - Identity: a FLAT/linear reference (pure carrier) is its own inverse — no
    pre-distortion is needed when there is no curvature to cancel.
  - Opposition: a curved reference produces an inverse whose curvature is the
    exact sign-reversal of the reference's, so the two sum to a pure plane (the
    warps cancel). The non-trivial reference is y-invariant (curvature in x
    only) — the regime where the 2D plane fit and the 1D row-mean fit agree, so
    the test does not bake in an unverified 2D-curvature assumption (that is the
    B.2 golden-part question).
  - Shape/unit contract: (H, W) float64 phase in radians.
"""
from __future__ import annotations

import numpy as np

from calibration import fit_tilt_line_1d, fit_tilt_plane
from pattern_generator import inverse_grating_phase

H, W = 32, 64
P_PERIOD = 40.0  # carrier period in pixels (matches the notebook/sealed core)


def _carrier() -> np.ndarray:
    """Pure linear carrier (2*pi/p)*X, y-invariant, shape (H, W)."""
    X = np.tile(np.arange(W, dtype=np.float64), (H, 1))
    return (2.0 * np.pi / P_PERIOD) * X


# ----------------------------------------------------------------------
# Identity: inverse of a flat/linear reference is the carrier itself.
# ----------------------------------------------------------------------
def test_flat_reference_inverse_is_identity_carrier():
    carrier = _carrier()
    inv = inverse_grating_phase(carrier)
    # A pure plane is recovered by the lstsq tilt fit; 2*P - carrier == carrier.
    np.testing.assert_allclose(
        inv,
        carrier,
        atol=1e-6,
        err_msg="flat/linear reference must invert to the plain carrier",
    )


# ----------------------------------------------------------------------
# Opposition: curved reference -> inverse curvature is the exact sign-flip.
# ----------------------------------------------------------------------
def test_curved_reference_inverse_opposes_warp():
    # y-invariant curvature: carrier + a quadratic-in-x bump tiled over rows.
    x = np.arange(W, dtype=np.float64)
    xc = (x - (W - 1) / 2.0) / W
    curvature_1d = 3.0 * xc**2          # rad, function of x only
    reference = _carrier() + np.tile(curvature_1d, (H, 1))

    inv = inverse_grating_phase(reference)

    # Same linear plane P for both (fit is linear: P(2P-phi) = P(phi)).
    plane, _ = fit_tilt_plane(reference)
    res_ref = reference - plane
    res_inv = inv - plane

    # The inverse's curvature is the exact negation of the reference's.
    np.testing.assert_allclose(
        res_inv, -res_ref, atol=1e-9,
        err_msg="inverse curvature must oppose the reference's warp",
    )
    # Equivalently: reference + inverse is a pure plane (warps cancel) -> the
    # discrete second difference along x is ~0.
    summed = reference + inv
    curv = np.diff(summed, n=2, axis=1)
    assert np.abs(curv).max() < 1e-9, "reference + inverse must be curvature-free"


def test_nontrivial_reference_stays_in_2d_1d_agreement_regime():
    # Documents that the opposition test lives where fit_tilt_plane (2D) and
    # fit_tilt_line_1d agree, so no 2D-curvature assumption is baked in.
    x = np.arange(W, dtype=np.float64)
    xc = (x - (W - 1) / 2.0) / W
    reference = _carrier() + np.tile(3.0 * xc**2, (H, 1))

    plane_2d, _ = fit_tilt_plane(reference)
    plane_1d, _ = fit_tilt_line_1d(reference)
    np.testing.assert_allclose(plane_2d, plane_1d, atol=1e-8)


# ----------------------------------------------------------------------
# Shape / unit contract.
# ----------------------------------------------------------------------
def test_output_shape_dtype_contract():
    reference = _carrier()
    inv = inverse_grating_phase(reference)
    assert inv.shape == (H, W)
    assert inv.dtype == np.float64
