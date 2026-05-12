"""End-to-end integration test for the Stage 2 module set.

Wires together every src/ module (geometry, synthetic_fringes,
phase_shifting, unwrapping, calibration, reconstruction) to reproduce
the notebook's Gaussian recovery using only public APIs — no inline
polyfits, no inline forward-model math, no shortcut to fixture
intermediates that the modules should produce themselves.

This is the Stage 2 exit criterion. If the test passes, the refactor
is complete.

Tolerances (from tests/conftest.py):
    ATOL_ANALYTICAL = 1e-12   (closed-form arithmetic)
    ATOL_PIPELINE   = 1e-8    (pipeline operations)

Recovery-quality bar:
    std_err < 2 * BASELINE_STD where BASELINE_STD = 1.7645046580428724e-05
    (recorded in notebook cell 20).

Deviation from the Stage 2.6 spec — step d
------------------------------------------
The task spec says to synthesize the object stack from
`project(phi3, geom)`. That would add the projector's perspective bias
(~17 rad at the array edge for theta=15 deg, a=2000) to the object
phase. A 1D tilt-fit calibration cannot remove the resulting quadratic
bias residual (~3 rad), which propagates to a height contamination
~6 orders of magnitude above the recovery-quality bar — `std_err`
would explode and the H_rec0 fixture match would fail catastrophically.

The notebook (cell 16) synthesizes from `phi3` directly without
applying `project()`, effectively simulating the world AFTER
inverse-grating correction (where the projector emits clean fringes).
The fixture was generated under that exact assumption. This test
follows the notebook to keep the fixture comparison meaningful;
`project()`'s correctness is independently validated in
tests/test_synthetic_fringes.py.
"""
from __future__ import annotations

import numpy as np

from conftest import ATOL_ANALYTICAL, ATOL_PIPELINE
from calibration import compute_inverse_phase, fit_tilt_line_1d
from geometry import SymmetricGeometry
from phase_shifting import extract_phase
from reconstruction import recover_object_height
from synthetic_fringes import project, synthesize_psi_stack
from unwrapping import unwrap_2d


BASELINE_STD = 1.7645046580428724e-05  # notebook cell 20


def test_pipeline_end_to_end_gaussian_recovery(regression_data):
    geom = SymmetricGeometry()
    H, W = geom.H, geom.W

    x = np.arange(W, dtype=np.float64)
    y = np.arange(H, dtype=np.float64)
    X, _ = np.meshgrid(x, y)

    deltas = [0.0, np.pi / 2.0, np.pi, 3.0 * np.pi / 2.0]

    # ----------------------------------------------------------------
    # Calibration leg: build biased flat-reference phase, recover it
    # through the PSI pipeline, derive phi2 via compute_inverse_phase.
    # ----------------------------------------------------------------
    uniform_phase = (2.0 * np.pi / geom.p) * X
    phi1_computed = project(uniform_phase, geom)

    flat_stack = synthesize_psi_stack(phi1_computed, deltas)
    flat_wrapped = extract_phase(flat_stack, deltas)
    phi1_unwrapped = unwrap_2d(flat_wrapped)

    phi2_computed = compute_inverse_phase(phi1_unwrapped)

    np.testing.assert_allclose(
        phi2_computed,
        regression_data["phi2"],
        atol=ATOL_ANALYTICAL,
        err_msg="calibration leg: phi2 must match fixture",
    )

    # ----------------------------------------------------------------
    # Object leg: build phi3 = carrier + height_phase, synthesize the
    # stack from phi3 directly (notebook cell 16; NOT project(phi3) —
    # see module docstring). Recover phi3_unwrapped via extract_phase +
    # unwrap_2d, derive phi_calibration via fit_tilt_line_1d, then run
    # recover_object_height for the end-to-end height recovery.
    # ----------------------------------------------------------------
    H_obj = regression_data["H_obj"]
    phi3 = (2.0 * np.pi / geom.p) * X + geom.height_to_phase(H_obj)

    object_stack = synthesize_psi_stack(phi3, deltas)

    object_wrapped = extract_phase(object_stack, deltas)
    phi3_unwrapped = unwrap_2d(object_wrapped)

    phi_calibration, _ = fit_tilt_line_1d(phi3_unwrapped)

    h_rec = recover_object_height(object_stack, phi_calibration, deltas, geom)
    h_rec0 = h_rec - h_rec.mean() + H_obj.mean()

    # ----------------------------------------------------------------
    # Recovery-quality bar (cell-20 baseline).
    # ----------------------------------------------------------------
    std_err = float((h_rec0 - H_obj).std())
    assert std_err < 2.0 * BASELINE_STD, (
        f"recovery std error {std_err:.4e} exceeds 2 x baseline "
        f"{BASELINE_STD:.4e}"
    )

    # ----------------------------------------------------------------
    # Belt-and-suspenders: bit-near-fixture match. Catches silent
    # divergence from the notebook's pipeline that the std bar might
    # not see (e.g., a shape change that happens to keep std small).
    # ----------------------------------------------------------------
    np.testing.assert_allclose(
        h_rec0,
        regression_data["H_rec0"],
        atol=ATOL_PIPELINE,
        err_msg="H_rec0 must match fixture to ATOL_PIPELINE",
    )
