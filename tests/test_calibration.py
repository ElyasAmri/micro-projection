"""Regression tests for calibration.fit_tilt_plane, fit_tilt_line_1d,
and compute_inverse_phase.

Three checks:

a. compute_inverse_phase(regression_data['phi1_unwrapped']) reproduces the
   fixture's phi2 to ATOL_ANALYTICAL. phi2 is analytically constructed
   from phi1_unwrapped via 2*P - phi1_unwrapped, so this is an analytical
   (not pipeline) comparison.

   Note on 1D vs 2D fit drift: the notebook computes P via a 1D
   row-mean polyfit, while compute_inverse_phase uses fit_tilt_plane
   (2D lstsq). For the notebook's effectively-y-invariant phi1_unwrapped
   (whose only y-variation is ULP-scale PSI noise), the two approaches
   differ by roughly m_y * Y_max ~ 1e-15, well below
   ATOL_ANALYTICAL = 1e-12.

b. fit_tilt_plane on a synthetic pure-tilt P_true = 0.01*x + 0.02*y + 0.5
   recovers (m_x, m_y, c) to atol=1e-12 and the plane array to
   ATOL_ANALYTICAL. Isolates fit_tilt_plane from fixture noise.

c. fit_tilt_line_1d on a synthetic pure-x tilt P_true = 0.01*x + 0.5
   recovers (m, c) and the tiled plane exactly (atol=1e-12). Isolates
   the 1D fit from the rest of the pipeline.
"""
from __future__ import annotations

import numpy as np

from conftest import ATOL_ANALYTICAL
from calibration import compute_inverse_phase, fit_tilt_line_1d, fit_tilt_plane


def test_compute_inverse_phase_matches_phi2_fixture(regression_data):
    phi2_computed = compute_inverse_phase(regression_data["phi1_unwrapped"])
    np.testing.assert_allclose(
        phi2_computed,
        regression_data["phi2"],
        atol=ATOL_ANALYTICAL,
        err_msg="compute_inverse_phase must reproduce the notebook's phi2",
    )


def test_fit_tilt_plane_recovers_pure_tilt():
    H, W = 480, 640
    x = np.arange(W, dtype=np.float64)
    y = np.arange(H, dtype=np.float64)
    X, Y = np.meshgrid(x, y)

    m_x_true, m_y_true, c_true = 0.01, 0.02, 0.5
    P_true = m_x_true * X + m_y_true * Y + c_true

    plane, (m_x, m_y, c) = fit_tilt_plane(P_true)

    assert abs(m_x - m_x_true) < 1e-12, f"m_x={m_x}, expected {m_x_true}"
    assert abs(m_y - m_y_true) < 1e-12, f"m_y={m_y}, expected {m_y_true}"
    assert abs(c - c_true) < 1e-12, f"c={c}, expected {c_true}"

    np.testing.assert_allclose(
        plane,
        P_true,
        atol=ATOL_ANALYTICAL,
        err_msg="fit_tilt_plane must reconstruct a pure plane exactly",
    )


def test_fit_tilt_line_1d_matches_inline_polyfit():
    """fit_tilt_line_1d recovers a pure-x tilt and matches notebook cell 18 exactly."""
    H, W = 480, 640
    x = np.arange(W, dtype=np.float64)
    y = np.arange(H, dtype=np.float64)
    X, _ = np.meshgrid(x, y)

    m_true, c_true = 0.01, 0.5
    P_true = m_true * X + c_true  # y-invariant by construction

    plane, (m, c) = fit_tilt_line_1d(P_true)

    assert abs(m - m_true) < 1e-12, f"m={m}, expected {m_true}"
    assert abs(c - c_true) < 1e-12, f"c={c}, expected {c_true}"

    np.testing.assert_allclose(
        plane,
        P_true,
        atol=1e-12,
        err_msg="fit_tilt_line_1d must reconstruct a y-invariant tilt exactly",
    )

    # Belt-and-suspenders: the returned plane equals the literal
    # notebook-cell-18 construction.
    profile_ref = P_true.mean(axis=0)
    m_ref, c_ref = np.polyfit(x, profile_ref, 1)
    plane_ref = np.tile(m_ref * x + c_ref, (H, 1))
    np.testing.assert_array_equal(
        plane,
        plane_ref,
        err_msg="fit_tilt_line_1d must be bit-for-bit equal to inline polyfit + tile",
    )
