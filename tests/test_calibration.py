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
    H, W = 550, 680
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
    H, W = 550, 680
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


# ======================================================================
# A.3b — tilt-flip on NON-project curvature (validation hygiene).
#
# This breaks the INVERSE half of the inverse-FPP tautology. The A.2 closure
# tests (tests/test_inverse_fpp.py) pass for ANY self-consistent project() bias,
# because the inverse grating is derived empirically from project()'s OWN output
# -- so the same closed form sits on both sides. Here the reference is built
# directly from a KNOWN tilted plane plus a KNOWN curvature that project() can
# NEVER emit, and the expectation is built from the GEOMETRIC definition of the
# flip (reflect curvature about the true plane), NOT from compute_inverse_phase's
# output. The test therefore fails if the tilt-flip `2P - phi` is wrong,
# independent of project()'s bias formula.
# ======================================================================
def test_tilt_flip_reflects_arbitrary_curvature_about_known_plane():
    """compute_inverse_phase reflects curvature about the plane (2P - phi), checked
    against a hand-built reference project() never produces.

    Reference: ref = P_known + curv_known where
      - P_known   = m_x*X + m_y*Y + c, a known non-zero TILTED plane;
      - curv_known = an off-center 2D Gaussian (x AND y structure, localized)
        plus an x-cubic (odd) -- categorically unlike project()'s column-only
        even quadratic (4*pi/p)*x^2*tan(theta)/a.

    Assertions:
      (i)  fit_tilt_plane(ref) recovers P_known. curv_known is pre-orthogonalized
           to the {1, x, y} basis with an INDEPENDENT inline lstsq (test
           scaffolding, NOT fit_tilt_plane), so it leaks nothing into the plane;
           a non-orthogonal curvature would make P_fitted != P_known.
      (ii) the deviation of compute_inverse_phase(ref) about P_known equals MINUS
           the deviation of ref about P_known -- curvature negated, tilt
           preserved. The expectation (-curv_known, equivalently 2*P_known - ref)
           is built from the KNOWN plane/curvature, never from the function's
           output, so referencing the TRUE plane (not the fitted one) keeps this
           from collapsing into a restatement of the function body.

    Tolerance: residuals floor at ~7e-14 same-machine (measured); atol 1e-10
    leaves headroom for cross-build lstsq/BLAS ULP drift (B.4 determinism note)
    while sitting ~10 orders below the ~4 rad curv_known signal that a wrong flip
    (missing factor 2, sign error) would corrupt.
    """
    H, W = 550, 680
    x = np.arange(W, dtype=np.float64)
    y = np.arange(H, dtype=np.float64)
    X, Y = np.meshgrid(x, y)

    # Known tilted plane (all three coefficients non-zero).
    m_x, m_y, c = 0.013, -0.021, 2.5
    P_known = m_x * X + m_y * Y + c

    # A curvature project() NEVER produces: off-center 2D Gaussian + an x-cubic.
    raw_curv = (
        5.0 * np.exp(
            -(((X - 0.62 * W) ** 2 + (Y - 0.40 * H) ** 2) / (2.0 * 70.0 ** 2))
        )
        + 8e-8 * (X - W / 2.0) ** 3
    )

    # Pre-orthogonalize raw_curv to {1, x, y} via an INDEPENDENT inline lstsq
    # (not fit_tilt_plane) so curv_known carries ~zero plane component and the
    # plane fit below recovers P_known exactly.
    basis = np.column_stack([X.ravel(), Y.ravel(), np.ones(H * W, dtype=np.float64)])
    raw_plane_coef, _, _, _ = np.linalg.lstsq(basis, raw_curv.ravel(), rcond=None)
    curv_known = raw_curv - (basis @ raw_plane_coef).reshape(H, W)

    ref = P_known + curv_known

    ATOL = 1e-10  # see docstring: ~1500x the measured ~7e-14 same-machine floor

    # Premise guard: curv_known is a genuine non-trivial curvature (not a no-op
    # on a pure plane), so the flip is a real reflection.
    assert np.max(np.abs(curv_known)) > 1.0

    # (i) fit_tilt_plane recovers the known plane.
    plane_fit, (fmx, fmy, fc) = fit_tilt_plane(ref)
    np.testing.assert_allclose(
        plane_fit, P_known, rtol=0.0, atol=ATOL,
        err_msg="fit_tilt_plane must recover the known tilted plane",
    )
    assert abs(fmx - m_x) < 1e-9
    assert abs(fmy - m_y) < 1e-9
    assert abs(fc - c) < 1e-9

    # (ii) the tilt-flip negates the curvature about the KNOWN plane while
    # preserving the tilt. Expectation built geometrically from P_known/curv_known.
    out = compute_inverse_phase(ref)
    np.testing.assert_allclose(
        out - P_known, -(ref - P_known), rtol=0.0, atol=ATOL,
        err_msg=(
            "deviation about the known plane must be negated by the tilt-flip "
            "(2P - phi reflects curvature, preserves tilt)"
        ),
    )
    # Equivalently, the full reflected field: out == 2*P_known - ref. Stated
    # explicitly to show the expectation is the geometric reflection, not the
    # function's own output.
    np.testing.assert_allclose(
        out, 2.0 * P_known - ref, rtol=0.0, atol=ATOL,
        err_msg="compute_inverse_phase must equal the geometric reflection 2*P_known - ref",
    )
