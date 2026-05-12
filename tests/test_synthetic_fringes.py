"""Regression tests for synthetic_fringes.project() and synthesize_psi_stack().

Checks performed:

a. project() Taylor branch reproduces the notebook's analytical phi1 against
   the regression fixture, using SymmetricGeometry (whose defaults match the
   notebook parameters).

b. project() is geometry-type-independent: HybridGeometry and
   SymmetricGeometry produce bit-identical output when their bias parameters
   (p, theta_projector, a) match. This locks the architectural constraint
   that project() does not read lambda_eq.

c. synthesize_psi_stack() returns A + B * cos(phase + delta_k) for each
   frame, matching the notebook cell 4 formula.

Tolerances come from tests/conftest.py:
    ATOL_ANALYTICAL = 1e-12   (closed-form arrays)
    ATOL_PIPELINE   = 1e-8    (pipeline arrays)
"""
from __future__ import annotations

import numpy as np

from conftest import ATOL_ANALYTICAL
from geometry import HybridGeometry, SymmetricGeometry
from synthetic_fringes import project, synthesize_psi_stack


def test_project_taylor_matches_phi1(regression_data):
    """project() Taylor branch reproduces notebook cell 3's phi1 array.

    SymmetricGeometry is used because the regression fixture was generated
    from the notebook, which uses the symmetric parameters (M=1, p=40,
    theta=15 deg, a=2000). For project() specifically the geometry type
    does not matter (see test_project_is_lambda_eq_independent), but the
    explicit choice matches the fixture's provenance.
    """
    geom = SymmetricGeometry()
    H, W = geom.H, geom.W
    X = np.tile(np.arange(W, dtype=np.float64), (H, 1))
    uniform_phase = (2.0 * np.pi / geom.p) * X

    phi1_computed = project(uniform_phase, geom)

    np.testing.assert_allclose(
        phi1_computed,
        regression_data["phi1"],
        atol=ATOL_ANALYTICAL,
        err_msg="project() Taylor branch must reproduce notebook's phi1",
    )


def test_project_is_lambda_eq_independent():
    """HybridGeometry and SymmetricGeometry yield identical project() output.

    Both default to p=40, theta(_projector)=15 deg, a=2000. Their M and
    therefore lambda_eq differ, but project() reads only the bias parameters
    and must be invariant to lambda_eq. This test locks that contract.
    """
    hg = HybridGeometry()
    sg = SymmetricGeometry()

    assert hg.p == sg.p
    assert hg.theta_projector == sg.theta_projector
    assert hg.a == sg.a
    # Sanity: the two geometries do disagree elsewhere.
    assert hg.equivalent_wavelength() != sg.equivalent_wavelength()

    H, W = sg.H, sg.W
    X = np.tile(np.arange(W, dtype=np.float64), (H, 1))
    uniform_phase = (2.0 * np.pi / sg.p) * X

    out_hg = project(uniform_phase, hg)
    out_sg = project(uniform_phase, sg)

    np.testing.assert_allclose(
        out_hg,
        out_sg,
        atol=1e-15,
        err_msg=(
            "project() must depend only on (p, theta_projector, a) and "
            "produce identical output across geometry types"
        ),
    )


def test_project_exact_matches_taylor_at_origin():
    """At column x=0, the exact and Taylor branches agree to machine zero.

    Both forms have bias=0 at x=0 (carrier_exact(0) = carrier_input(0) = 0
    and (4*pi/p)*x^2*tan/a = 0), so the two outputs must be bit-identical
    on the x=0 column for any input_phase.
    """
    geom = SymmetricGeometry()
    H, W = geom.H, geom.W
    X = np.tile(np.arange(W, dtype=np.float64), (H, 1))
    uniform_phase = (2.0 * np.pi / geom.p) * X

    out_taylor = project(uniform_phase, geom, model="taylor")
    out_exact = project(uniform_phase, geom, model="exact")

    np.testing.assert_allclose(
        out_exact[:, 0],
        out_taylor[:, 0],
        atol=1e-15,
        err_msg=(
            "project(): exact and taylor branches must agree on x=0 column "
            "to machine zero (bias vanishes there for both models)"
        ),
    )


def test_project_exact_taylor_consistency():
    """Reproduce notebook cell 25's measurement: ratio = diff_max / expected_scale.

    Cell 25 defines

        expected_scale = (W * tan(theta) / a)^2 * (2*pi / p1) * W

    as the magnitude of the leading u^2 truncation remainder at x=W, where
    u = 2*x*tan(theta)/a. The measured ratio of `diff_max` over this scale
    is expected to be O(1) — cell 25 passes if `0.1 < ratio < 10`.

    This test re-runs that measurement against the module's exact and
    Taylor branches (no inline analytical formula on either side, except
    `expected_scale` itself which is the truncation-error scale, not a
    model implementation).
    """
    geom = SymmetricGeometry()
    H, W = geom.H, geom.W
    X = np.tile(np.arange(W, dtype=np.float64), (H, 1))
    uniform_phase = (2.0 * np.pi / geom.p) * X

    phi_taylor = project(uniform_phase, geom, model="taylor")
    phi_exact = project(uniform_phase, geom, model="exact")

    diff = phi_exact - phi_taylor
    diff_max = float(np.max(np.abs(diff)))

    expected_scale = (
        (W * np.tan(geom.theta_projector) / geom.a) ** 2
        * (2.0 * np.pi / geom.p)
        * W
    )
    ratio = diff_max / expected_scale

    assert 0.1 < ratio < 10.0, (
        f"exact-vs-taylor truncation ratio {ratio:.4f} outside (0.1, 10); "
        f"diff_max={diff_max:.4e}, expected_scale={expected_scale:.4e}"
    )
    assert diff_max > 0.0, "exact and Taylor branches produced identical output"


def test_project_exact_lambda_eq_independent():
    """HybridGeometry and SymmetricGeometry yield identical exact-branch output.

    Same invariant as `test_project_is_lambda_eq_independent` but for
    `model='exact'`. The exact branch must read only (p, theta_projector, a)
    — never lambda_eq — so the two geometry types must produce bit-identical
    output when those three parameters agree.
    """
    hg = HybridGeometry()
    sg = SymmetricGeometry()

    assert hg.p == sg.p
    assert hg.theta_projector == sg.theta_projector
    assert hg.a == sg.a
    assert hg.equivalent_wavelength() != sg.equivalent_wavelength()

    H, W = sg.H, sg.W
    X = np.tile(np.arange(W, dtype=np.float64), (H, 1))
    uniform_phase = (2.0 * np.pi / sg.p) * X

    out_hg = project(uniform_phase, hg, model="exact")
    out_sg = project(uniform_phase, sg, model="exact")

    np.testing.assert_allclose(
        out_hg,
        out_sg,
        atol=1e-15,
        err_msg=(
            "project(model='exact') must depend only on (p, theta_projector, a) "
            "and produce identical output across geometry types"
        ),
    )


def test_project_exact_denom_positive_default_geometry():
    """The exact branch's denom-positivity guard does NOT fire under defaults.

    Under the operational default geometry (p=40, theta=15 deg, a=2000,
    W=640), denom = 1 + 2*X*tan(theta)/a ranges from 1.0 at x=0 to
    ~1.17 at x=W-1, comfortably > 0. This test smoke-checks the guard
    against silent regressions in the default parameter values (e.g., a
    future operator setting a=-2000 or theta=80 degrees would trip it).
    """
    for geom in (HybridGeometry(), SymmetricGeometry()):
        H, W = geom.H, geom.W
        X = np.tile(np.arange(W, dtype=np.float64), (H, 1))
        uniform_phase = (2.0 * np.pi / geom.p) * X
        # If the guard fires, this raises ValueError and the test fails.
        out = project(uniform_phase, geom, model="exact")
        assert out.shape == uniform_phase.shape
        assert np.all(np.isfinite(out)), "exact branch produced non-finite output"


def test_psi_stack_matches_notebook_formula(regression_data):
    """synthesize_psi_stack frame k equals A + B * cos(phase + delta_k).

    Verified by reconstructing frame 0 (delta = 0) from regression_data['phi1']
    using the literal formula from notebook cell 4 and comparing.
    """
    phi1 = regression_data["phi1"]
    deltas = [0.0, np.pi / 2.0, np.pi, 3.0 * np.pi / 2.0]

    stack = synthesize_psi_stack(phi1, deltas)

    assert stack.shape == phi1.shape + (4,), f"unexpected shape {stack.shape}"
    assert stack.dtype == np.float64

    expected_frame_0 = 1.0 + 0.9 * np.cos(phi1)  # notebook A=1.0, B=0.9
    np.testing.assert_allclose(
        stack[..., 0],
        expected_frame_0,
        atol=ATOL_ANALYTICAL,
        err_msg="synthesize_psi_stack frame 0 must equal A + B*cos(phase + 0)",
    )
