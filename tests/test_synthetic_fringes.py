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
