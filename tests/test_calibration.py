"""Regression tests for calibration.fit_tilt_plane and compute_inverse_phase.

Two checks:

a. compute_inverse_phase(regression_data['phi1_unwrapped']) reproduces the
   fixture's phi2 to ATOL_ANALYTICAL. phi2 is analytically constructed
   from phi1_unwrapped via 2*P - phi1_unwrapped, so this is an analytical
   (not pipeline) comparison.

   Note on 1D vs 2D fit drift: the notebook computes P via a 1D
   row-mean polyfit, while calibration.py uses a true 2D lstsq fit.
   For the notebook's effectively-y-invariant phi1_unwrapped (whose only
   y-variation is ULP-scale PSI noise), the two approaches differ by
   roughly m_y * Y_max ~ 1e-15, well below ATOL_ANALYTICAL = 1e-12.

b. fit_tilt_plane on a synthetic pure-tilt P_true = 0.01*x + 0.02*y + 0.5
   recovers (m_x, m_y, c) to atol=1e-12 and the plane array to
   ATOL_ANALYTICAL. Isolates fit_tilt_plane from fixture noise.
"""
from __future__ import annotations

import numpy as np

from conftest import ATOL_ANALYTICAL
from calibration import compute_inverse_phase, fit_tilt_plane


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
