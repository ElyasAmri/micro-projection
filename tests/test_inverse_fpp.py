"""Tests for the closed inverse-FPP step, pipeline.run_inverse_fpp (Stage 6 A.2).

SCOPE / HONESTY (the A.3 / Q4 caveat): the same affine `project` model creates
the object capture and is inverted by the inverse grating derived from the
reference, so the closure here is true by construction. These tests prove
CONSISTENCY — composition, sign conventions, unwrap, and self-calibration are
wired correctly, and the inverse grating exactly inverts the forward bias. They
are NOT physics validation; that is D.3-vs-B.4 (a real projector whose bias is
not the analytic Taylor model).

The substance of A.2 (beyond "recovered == object"):
  1. bias_cancellation: WITHOUT the inverse grating, project()-on-the-object
     blows recovery up; WITH it, the same biased capture recovers cleanly.
  2. non_identity: the inverse grating for a biased flat reference is NOT the
     carrier — it carries the bias-correction curvature (pins the Q2 correction).
  3. flat-object and simple-object pass conditions (Q2).
"""
from __future__ import annotations

import numpy as np

from conftest import ATOL_PIPELINE
from calibration import fit_tilt_line_1d
from geometry import SymmetricGeometry
from pattern_generator import inverse_grating_phase
from phase_shifting import extract_phase
from pipeline import run_inverse_fpp
from reconstruction import recover_object_height
from synthetic_fringes import project, synthesize_psi_stack
from unwrapping import unwrap_2d

BASELINE_STD = 1.7645046580428724e-05  # notebook cell 20 recovery-quality bar
DELTAS = [0.0, np.pi / 2.0, np.pi, 3.0 * np.pi / 2.0]


def _carrier(geom) -> np.ndarray:
    X = np.tile(np.arange(geom.W, dtype=np.float64), (geom.H, 1))
    return (2.0 * np.pi / geom.p) * X


# ----------------------------------------------------------------------
# (1) THE CORE A.2 CLAIM — bias cancellation makes project()-on-object safe.
# ----------------------------------------------------------------------
def test_inverse_grating_cancels_projector_bias(regression_data):
    geom = SymmetricGeometry()  # theta=15deg, a=2000 -> ~17 rad bias at edge
    H_obj = regression_data["H_obj"]
    carrier = _carrier(geom)

    # --- WITHOUT the inverse grating: synthesize the object straight through
    # project() (the naive path test_pipeline_synthetic.py:40-56 warns about).
    naive_phase = project(carrier + geom.height_to_phase(H_obj), geom)
    naive_stack = synthesize_psi_stack(naive_phase, DELTAS)
    naive_cal, _ = fit_tilt_line_1d(unwrap_2d(extract_phase(naive_stack, DELTAS)))
    h_naive = recover_object_height(naive_stack, naive_cal, DELTAS, geom)
    h_naive = h_naive - h_naive.mean() + H_obj.mean()
    naive_std = float((h_naive - H_obj).std())

    # --- WITH the inverse grating (same biased project on the object leg).
    recovered = run_inverse_fpp(np.zeros_like(H_obj), H_obj, geom, DELTAS)
    good_std = float((recovered - H_obj).std())

    # The naive path is blown up; the corrected path meets the recovery bar.
    assert naive_std > 1.0, f"naive bias contamination unexpectedly small: {naive_std}"
    assert good_std < 2.0 * BASELINE_STD, f"corrected recovery too coarse: {good_std}"
    assert naive_std > 1e3 * good_std  # the contrast that IS A.2


# ----------------------------------------------------------------------
# (2) The inverse grating is NON-IDENTITY once the projector is biased.
# ----------------------------------------------------------------------
def test_inverse_grating_is_non_identity_for_biased_reference():
    geom = SymmetricGeometry()
    carrier = _carrier(geom)
    ref_phase = project(carrier, geom)            # biased flat reference
    phi_projected = inverse_grating_phase(ref_phase)

    # It must NOT collapse to the plain carrier...
    assert not np.allclose(phi_projected, carrier, atol=1e-3), (
        "inverse grating collapsed to the carrier — bias correction lost"
    )
    # ...and the difference carries genuine curvature (not just an offset/tilt):
    diff = phi_projected - carrier
    second_diff = np.diff(diff, n=2, axis=1)
    assert np.abs(second_diff).max() > 1e-6, (
        "inverse grating carries no curvature — bias pre-distortion missing"
    )


# ----------------------------------------------------------------------
# (3a) Flat object -> recovers flat (bias fully cancelled).
# ----------------------------------------------------------------------
def test_flat_object_recovers_flat():
    geom = SymmetricGeometry()
    flat = np.zeros((geom.H, geom.W), dtype=np.float64)
    recovered = run_inverse_fpp(flat, flat, geom, DELTAS)
    assert np.abs(recovered).max() < ATOL_PIPELINE


# ----------------------------------------------------------------------
# (3b) Simple object -> recovers to the validated pipeline result.
# ----------------------------------------------------------------------
def test_simple_object_recovers_to_fixture(regression_data):
    geom = SymmetricGeometry()
    H_obj = regression_data["H_obj"]
    recovered = run_inverse_fpp(np.zeros_like(H_obj), H_obj, geom, DELTAS)

    std_err = float((recovered - H_obj).std())
    assert std_err < 2.0 * BASELINE_STD

    # Strongest: identical to the notebook/pipeline's recovered H_rec0, because
    # the cancelled capture reduces to (linear carrier + height_phase).
    np.testing.assert_allclose(
        recovered, regression_data["H_rec0"], atol=ATOL_PIPELINE,
        err_msg="inverse-FPP recovery must match the validated H_rec0 fixture",
    )


# ----------------------------------------------------------------------
# Single-step is loop-wrappable: feed the output back as the next reference.
# ----------------------------------------------------------------------
def test_single_step_is_loop_wrappable(regression_data):
    geom = SymmetricGeometry()
    H_obj = regression_data["H_obj"]

    rec1 = run_inverse_fpp(np.zeros_like(H_obj), H_obj, geom, DELTAS)
    # Previous output is a valid next reference (height in, height out).
    rec2 = run_inverse_fpp(rec1, H_obj, geom, DELTAS)

    assert np.all(np.isfinite(rec2)), "second iteration produced non-finite values"
    # Structural stability only (convergence is deferred): the extra iteration
    # does not diverge — it stays on the object's scale, not orders above it.
    bound = 100.0 * (float(np.abs(H_obj).max()) + 1.0)
    assert float(np.abs(rec2).max()) < bound
