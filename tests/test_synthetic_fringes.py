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
import pytest

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


# ======================================================================
# A.3a — project() AFFINE-STRUCTURE check (validation hygiene).
#
# The inverse-FPP loop's exact-cancellation premise (pipeline.run_inverse_fpp)
# is that `project` is a PURE PHASE TRANSLATION: project(phi) = phi - b(x), with
# the bias `b` a function of the column index ONLY and INDEPENDENT of the phase
# argument. These two tests pin that affine STRUCTURE for both model branches.
#
# SCOPE / HONESTY: they do NOT validate the numeric correctness of b(x). A
# self-consistent WRONG bias would still cancel in the inverse-FPP loop (the
# inverse grating is derived empirically from project()'s own output), so the
# physical correctness of the bias stays the hardware oracle (D.3-vs-B.4: a real
# projector whose bias is not the analytic Taylor model). These complement the
# tautology documented in tests/test_inverse_fpp.py's module docstring by
# pinning the one premise that IS checkable in sim: the affine structure.
#
# Float floor: the translation identity is EXACT in real arithmetic; in double
# precision it floors at ~1.4e-14 at the ~15-17 rad bias magnitude (measured for
# both branches). ATOL_ANALYTICAL = 1e-12 sits ~70x above that floor and ~12
# orders below any real phase-dependent contamination (which would be O(0.1)+).
# ======================================================================
@pytest.mark.parametrize("model", ["taylor", "exact"])
@pytest.mark.parametrize("shape", [(550, 680), (64, 100), (200, 320)])
def test_project_is_pure_phase_translation(model, shape):
    """project(phi1) - project(phi2) == phi1 - phi2: the bias is phase-independent.

    Pins the AFFINE STRUCTURE the inverse-FPP exact-cancellation premise relies
    on. Two arbitrary, structurally-different phase maps -- one of them
    height-modulated on the carrier (a realistic object-phase argument) -- over
    several grid shapes. The expectation is built STRUCTURALLY (the difference of
    two phase maps), with no reference to b(x)'s formula: if any phase-DEPENDENT
    term ever entered project, the bias would not cancel in the difference and
    this fails.

    NOT a numeric check of b(x) (a self-consistent wrong bias still cancels);
    that is the D.3-vs-B.4 hardware oracle.
    """
    geom = SymmetricGeometry()
    H, W = shape
    X = np.tile(np.arange(W, dtype=np.float64), (H, 1))
    Y = np.tile(np.arange(H, dtype=np.float64).reshape(-1, 1), (1, W))
    carrier = (2.0 * np.pi / geom.p) * X

    rng = np.random.default_rng(20240607)
    phi1 = (
        0.5 * np.sin(X / 13.0)
        + 0.2 * np.cos(Y / 9.0)
        + 0.01 * rng.standard_normal((H, W))
    )
    bump = 3.0 * np.exp(
        -(((X - W / 2.0) ** 2 + (Y - H / 2.0) ** 2) / (2.0 * 70.0 ** 2))
    )
    phi2 = carrier + bump  # height-modulated phase argument

    delta_proj = project(phi1, geom, model=model) - project(phi2, geom, model=model)
    delta_phase = phi1 - phi2

    np.testing.assert_allclose(
        delta_proj,
        delta_phase,
        rtol=0.0,
        atol=ATOL_ANALYTICAL,
        err_msg=(
            f"project(model={model!r}) is not a pure phase translation: the bias "
            "must be independent of the phase argument so it cancels in a "
            "difference (the inverse-FPP exact-cancellation premise)."
        ),
    )


@pytest.mark.parametrize("model", ["taylor", "exact"])
def test_project_zero_offset_is_minus_bias(model):
    """project(zeros) == -b(x): the translation offset equals the column bias.

    Plus two structural facts measured to hold exactly: the offset is
    row-independent (b depends on the column only) and vanishes at x=0.

    TYPO-GUARD caveat: b(x) here is RE-TYPED from project's own formula line, so
    this confirms the offset equals the DOCUMENTED bias -- a wiring/typo guard,
    NOT an independent validation of the bias physics (that is the D.3-vs-B.4
    hardware oracle). It pairs with test_project_is_pure_phase_translation, whose
    expectation needs no formula at all.
    """
    geom = SymmetricGeometry()
    H, W = 550, 680
    X = np.tile(np.arange(W, dtype=np.float64), (H, 1))
    offset = project(np.zeros((H, W), dtype=np.float64), geom, model=model)

    # Structural: the offset is column-only (every row identical) ...
    np.testing.assert_array_equal(
        offset,
        np.tile(offset[0, :], (H, 1)),
        err_msg="project(zeros) offset must be row-independent (column-only bias)",
    )
    # ... and vanishes at x=0 (both bias forms are 0 there).
    np.testing.assert_array_equal(
        offset[:, 0],
        np.zeros(H, dtype=np.float64),
        err_msg="project(zeros) offset must be zero on the x=0 column",
    )

    # The offset equals -b(x), with b re-typed from project's formula (typo-guard).
    if model == "taylor":
        b = (4.0 * np.pi / geom.p) * (
            X ** 2 * np.tan(geom.theta_projector) / geom.a
        )
    else:  # exact
        carrier_input = (2.0 * np.pi / geom.p) * X
        denom = 1.0 + 2.0 * X * np.tan(geom.theta_projector) / geom.a
        carrier_exact = (2.0 * np.pi / geom.p) * X / denom
        b = carrier_input - carrier_exact

    np.testing.assert_allclose(
        offset,
        -b,
        rtol=0.0,
        atol=ATOL_ANALYTICAL,
        err_msg=(
            f"project(zeros, model={model!r}) must equal -b(x), the documented "
            "column bias (typo-guard, not a physics check)."
        ),
    )
