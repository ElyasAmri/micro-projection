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
import pytest

from conftest import ATOL_PIPELINE
from calibration import fit_tilt_line_1d
from geometry import SymmetricGeometry
from pattern_generator import inverse_grating_phase
from phase_shifting import extract_phase
from pipeline import run_inverse_fpp, run_straight_fringe
from reconstruction import recover_object_height
from sampling import contrast_envelope
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


# ======================================================================
# A.2b — sampling fade live through the loop.
#
# HONEST SCOPE (noiseless): the envelope attenuates frame CONTRAST, not phase,
# identically across the N shifts, so extract_phase's arctan2 divides it out
# for any env > 0. Therefore enabling the fade leaves recovery UNCHANGED on
# well-sampled data (transparency — the correct noiseless behavior), and only
# collapses at env -> 0 (the sinc null, arctan2(0,0)). The gradual
# beyond-Nyquist wall (the B.3 claim) is an SNR effect that REQUIRES noise and
# is DEFERRED. These tests assert ONLY the noiseless truths; none add noise.
# ======================================================================
def _steep_ramp_object(geom, slope=26.0) -> np.ndarray:
    """Object heightmap with a flat left half and a steep ramp right half.

    `slope` ~ 26 drives the right-half local fringe frequency to ~0.37 cyc/px
    (env ~ 0.74) — a genuine contrast loss, but below 0.5 cyc/px so there is no
    unwrap aliasing and transparency can be asserted cleanly.
    """
    H, W = geom.H, geom.W
    obj = np.zeros((H, W), dtype=np.float64)
    cols = np.arange(W)
    right = cols >= W // 2
    obj[:, right] = slope * (cols[right] - W // 2)
    return obj


def _loop_object_phase(geom, reference_h, object_h):
    """Reconstruct the exact obj_phase run_inverse_fpp synthesizes (its step 3)."""
    X = np.tile(np.arange(geom.W, dtype=np.float64), (geom.H, 1))
    carrier = (2.0 * np.pi / geom.p) * X
    ref_phase = project(carrier, geom) + geom.height_to_phase(reference_h)
    phi_projected = inverse_grating_phase(ref_phase)
    return project(phi_projected, geom) + geom.height_to_phase(object_h)


def test_a2b_fill_factor_none_byte_identical(regression_data):
    """The default path is unchanged: explicit None == default, == A.2 result."""
    geom = SymmetricGeometry()
    H_obj = regression_data["H_obj"]
    ref = np.zeros_like(H_obj)

    rec_default = run_inverse_fpp(ref, H_obj, geom, DELTAS)
    rec_none = run_inverse_fpp(ref, H_obj, geom, DELTAS, fill_factor=None)
    np.testing.assert_array_equal(rec_default, rec_none)
    # And still the validated A.2 recovery.
    np.testing.assert_allclose(rec_none, regression_data["H_rec0"], atol=ATOL_PIPELINE)


def test_a2b_envelope_is_wired_into_loop_synthesis():
    """The fade reaches the frames the loop builds, attenuating contrast per env.

    run_inverse_fpp forwards fill_factor straight to synthesize_psi_stack
    (pipeline.py step 4). Synthesizing the loop's exact obj_phase with the
    envelope scales the per-pixel frame contrast by exactly `env`.
    """
    geom = SymmetricGeometry()
    obj_phase = _loop_object_phase(geom, np.zeros((geom.H, geom.W)),
                                   _steep_ramp_object(geom))
    env = contrast_envelope(obj_phase, fill_factor=1.0)

    stack_off = synthesize_psi_stack(obj_phase, DELTAS)
    stack_on = synthesize_psi_stack(obj_phase, DELTAS, fill_factor=1.0)
    c_off = stack_off.max(axis=-1) - stack_off.min(axis=-1)
    c_on = stack_on.max(axis=-1) - stack_on.min(axis=-1)

    # Frame contrast is attenuated by exactly the envelope (per pixel).
    np.testing.assert_allclose(c_on, env * c_off, rtol=1e-10, atol=1e-12)
    # The fade is non-trivial in the steep half and ~absent in the flat half.
    W = geom.W
    assert env[:, W // 2 + 2:].mean() < 0.9
    assert env[:, : W // 2 - 2].mean() > 0.99


def test_a2b_transparency_recovery_unchanged_with_fade():
    """Noiseless truth: with the fade ON, recovery is unchanged on env>0 data.

    Even on a genuinely faded object (steep half, env ~ 0.74), the recovered
    height with fill_factor=1.0 matches the no-fade recovery — extract_phase's
    arctan2 divides the contrast out. This is correct, NOT a bug; the fade
    needs a noise model to bite (deferred).
    """
    geom = SymmetricGeometry()
    obj = _steep_ramp_object(geom)
    ref = np.zeros_like(obj)

    rec_off = run_inverse_fpp(ref, obj, geom, DELTAS)
    rec_on = run_inverse_fpp(ref, obj, geom, DELTAS, fill_factor=1.0)
    np.testing.assert_allclose(rec_on, rec_off, atol=ATOL_PIPELINE)


def test_a2b_zero_contrast_null_is_defined_collapse():
    """env -> 0 (the sinc null) is a HARD singular collapse, not SNR roll-off.

    Where contrast vanishes the frames carry no fringe; extract_phase hits the
    degenerate arctan2(0,0) regime. With finite-precision deltas num and den
    are the ~1e-16 float residuals of the delta sums, so it returns a finite,
    defined-but-meaningless CONSTANT angle (no raise, no NaN) that is identical
    everywhere and carries no spatial fringe information — it does NOT recover
    the true phase. Labeled: contrast vanishes at the sinc null, not
    signal-to-noise degradation.
    """
    geom = SymmetricGeometry()
    A = 1.0
    zero_contrast = np.full((geom.H, geom.W, len(DELTAS)), A, dtype=np.float64)
    extracted = extract_phase(zero_contrast, DELTAS)

    assert np.all(np.isfinite(extracted)), "collapse must be defined, not NaN/raise"
    # Degenerate: the same residual-driven constant at every pixel — all spatial
    # fringe information is gone (not the true phase, just a flat garbage value).
    assert float(np.ptp(extracted)) < 1e-9


# ======================================================================
# A.4 — additive read noise: the sampling fade finally BITES.
#
# Read noise (fixed sigma) is added per-frame at the sensor stage, AFTER the
# envelope. Because it is independent per frame while B*env is common to all
# frames, it does NOT cancel in extract_phase's arctan2 (unlike env): low
# contrast + fixed sigma = low SNR = phase error ~ sigma/(B*env*sqrt(N)). All
# noisy assertions use a FIXED seed and a field statistic (RMS/std over a
# region), never a single pixel, so pass/fail is reproducible, not flaky.
# ======================================================================
def _region_rms(field, mask):
    """RMS of `field` over boolean column-`mask`, mean-removed (drop global tilt)."""
    vals = field[:, mask]
    return float(np.sqrt(((vals - vals.mean()) ** 2).mean()))


def test_a4_noise_off_is_byte_identical(regression_data):
    """noise_sigma=0.0 returns the existing arithmetic, untouched."""
    geom = SymmetricGeometry()
    H_obj = regression_data["H_obj"]
    ref = np.zeros_like(H_obj)
    X = np.tile(np.arange(geom.W, dtype=np.float64), (geom.H, 1))
    phase = (2.0 * np.pi / geom.p) * X

    # synthesize: sigma=0 ignores rng entirely (no RNG state touched).
    np.testing.assert_array_equal(
        synthesize_psi_stack(phase, DELTAS),
        synthesize_psi_stack(phase, DELTAS, noise_sigma=0.0, rng=np.random.default_rng(0)),
    )
    # loop: sigma=0 == default.
    np.testing.assert_array_equal(
        run_inverse_fpp(ref, H_obj, geom, DELTAS),
        run_inverse_fpp(ref, H_obj, geom, DELTAS, noise_sigma=0.0),
    )


def test_a4_noise_requires_explicit_rng():
    """noise_sigma>0 without an rng raises (no silent default-seed)."""
    geom = SymmetricGeometry()
    phase = np.zeros((geom.H, geom.W))
    obj = np.zeros((geom.H, geom.W))
    with pytest.raises(ValueError):
        synthesize_psi_stack(phase, DELTAS, noise_sigma=0.01, rng=None)
    with pytest.raises(ValueError):
        run_inverse_fpp(obj, obj, geom, DELTAS, noise_sigma=0.01, rng=None)


def test_a4_reproducible_with_seed(regression_data):
    """Same (object, sigma, seed) -> identical recovery; different seed -> different."""
    geom = SymmetricGeometry()
    H_obj = regression_data["H_obj"]
    ref = np.zeros_like(H_obj)

    r1 = run_inverse_fpp(ref, H_obj, geom, DELTAS, noise_sigma=0.01,
                         rng=np.random.default_rng(42))
    r2 = run_inverse_fpp(ref, H_obj, geom, DELTAS, noise_sigma=0.01,
                         rng=np.random.default_rng(42))
    np.testing.assert_array_equal(r1, r2)

    r3 = run_inverse_fpp(ref, H_obj, geom, DELTAS, noise_sigma=0.01,
                         rng=np.random.default_rng(7))
    assert not np.allclose(r1, r3)


def test_a4_per_frame_independence_is_required():
    """Noise must be (H,W,N) per frame; an (H,W) map broadcast across k cancels.

    Pins Q1: per-frame noise produces real phase error; the same-magnitude
    noise as a k-common map cancels in arctan2 (Sum sin/cos delta ~ 0) and
    leaves ~nothing. If the model ever drew (H,W) and broadcast, err_func would
    collapse to err_kcommon and this fails.
    """
    geom = SymmetricGeometry()
    # Non-wrapping phase (0..1 rad): avoids +-pi wrap boundaries, where a tiny
    # perturbation would flip pixels by 2*pi and pollute the wrapped-phase diff.
    X = np.tile(np.arange(geom.W, dtype=np.float64), (geom.H, 1))
    phase = X / geom.W
    clean = synthesize_psi_stack(phase, DELTAS)
    phi_clean = extract_phase(clean, DELTAS)
    sigma = 0.05

    # The model's output (per-frame independent).
    noisy = synthesize_psi_stack(phase, DELTAS, noise_sigma=sigma,
                                 rng=np.random.default_rng(0))
    err_func = float((extract_phase(noisy, DELTAS) - phi_clean).std())

    # Counterfactual: the SAME-scale noise as one (H,W) map added to every frame.
    n_map = np.random.default_rng(0).normal(scale=sigma, size=clean.shape[:2])
    err_kcommon = float((extract_phase(clean + n_map[..., None], DELTAS) - phi_clean).std())

    assert err_func > 1e-3, "per-frame noise must produce real phase error"
    assert err_kcommon < 1e-9, "a k-common map must cancel in arctan2"


def test_a4_wall_bites_faded_region_degrades(regression_data):
    """THE A.4 PAYOFF: with noise on, the faded region degrades, the flat does not.

    A steep ramp object drives the right half to ~0.4 cyc/px (alias-free, so the
    relationship stays smooth) while the left half stays at the carrier (~0.025).
    fill_factor=2.0 is a TEST construction that places the contrast roll-off
    inside the alias-free band (env_right ~ 0.2, env_left ~ 1), isolating the
    noise mechanism from unwrap aliasing. With fixed-sigma read noise, the
    recovered-height error scales ~1/env, so the faded half degrades materially
    more than the flat half. Fixed seed + region RMS -> reproducible.
    """
    geom = SymmetricGeometry()
    obj = _steep_ramp_object(geom, slope=28.0)
    ref = np.zeros_like(obj)
    W = geom.W

    # Document the operating point: roll-off lands in the alias-free band.
    obj_phase = _loop_object_phase(geom, ref, obj)
    env = contrast_envelope(obj_phase, fill_factor=2.0)
    flat_mask = np.arange(W) < W // 2 - 3
    faded_mask = np.arange(W) >= W // 2 + 3
    assert env[:, faded_mask].mean() < 0.35
    assert env[:, flat_mask].mean() > 0.9

    rec_clean = run_inverse_fpp(ref, obj, geom, DELTAS, fill_factor=2.0)
    rec_noisy = run_inverse_fpp(ref, obj, geom, DELTAS, fill_factor=2.0,
                                noise_sigma=0.01, rng=np.random.default_rng(0))
    err = rec_noisy - rec_clean  # isolates the noise-induced error

    faded_rms = _region_rms(err, faded_mask)
    flat_rms = _region_rms(err, flat_mask)
    # Gradual wall: faded-region error is materially larger (expect ~4x; assert
    # a comfortable >2.5x, well clear of a knife-edge).
    assert faded_rms > 2.5 * flat_rms


def test_a4_more_frames_recover_further_into_fade(regression_data):
    """Finding #2: N=8 averages noise down vs N=4 (~1/sqrt(2)).

    Flat object, env~1 everywhere, same sigma and seed: recovered-height noise
    std scales ~1/sqrt(N), so N=8 < N=4. Field std over many pixels makes the
    statistic stable for a single seed.
    """
    geom = SymmetricGeometry()
    flat = np.zeros((geom.H, geom.W), dtype=np.float64)
    deltas4 = [2.0 * np.pi * k / 4 for k in range(4)]
    deltas8 = [2.0 * np.pi * k / 8 for k in range(8)]

    clean4 = run_inverse_fpp(flat, flat, geom, deltas4, fill_factor=1.0)
    clean8 = run_inverse_fpp(flat, flat, geom, deltas8, fill_factor=1.0)
    noisy4 = run_inverse_fpp(flat, flat, geom, deltas4, fill_factor=1.0,
                             noise_sigma=0.02, rng=np.random.default_rng(0))
    noisy8 = run_inverse_fpp(flat, flat, geom, deltas8, fill_factor=1.0,
                             noise_sigma=0.02, rng=np.random.default_rng(0))

    err4 = float((noisy4 - clean4).std())
    err8 = float((noisy8 - clean8).std())
    assert err8 < 0.9 * err4  # expect ~0.71; assert comfortably below 1.0


# ======================================================================
# B.1 — straight-fringe (failing) vs inverse-FPP (corrected) before/after.
# The two sibling producers the Recovered Surface tab selects between.
# ======================================================================
def test_b1_straight_fringe_fails_where_inverse_fpp_recovers(regression_data):
    """The before/after is real: same object, same projector bias — only the
    inverse-grating correction differs. Straight-fringe recovery is contaminated
    by orders of magnitude; inverse-FPP meets the recovery bar."""
    geom = SymmetricGeometry()
    H_obj = regression_data["H_obj"]

    rec_inv = run_inverse_fpp(np.zeros_like(H_obj), H_obj, geom, DELTAS)
    rec_str = run_straight_fringe(H_obj, geom, DELTAS)

    err_inv = float((rec_inv - H_obj).std())
    err_str = float((rec_str - H_obj).std())

    assert err_inv < 2.0 * BASELINE_STD, f"inverse-FPP too coarse: {err_inv}"
    assert err_str > 1.0, f"straight-fringe should be blown up: {err_str}"
    assert err_str > 1e3 * err_inv  # the before/after separation


def test_b1_straight_fringe_has_param_parity_with_inverse_fpp():
    """run_straight_fringe accepts the SAME fill_factor/noise_sigma/rng so the
    before/after compares like-for-like (Stage 6 B.1 decision 2)."""
    geom = SymmetricGeometry()
    obj = np.zeros((geom.H, geom.W), dtype=np.float64)

    # Parity: noise requires an explicit rng, same as run_inverse_fpp.
    with pytest.raises(ValueError):
        run_straight_fringe(obj, geom, DELTAS, noise_sigma=0.01, rng=None)

    # Parity: fill_factor + seeded noise run and reproduce.
    r1 = run_straight_fringe(obj, geom, DELTAS, fill_factor=1.0,
                             noise_sigma=0.01, rng=np.random.default_rng(3))
    r2 = run_straight_fringe(obj, geom, DELTAS, fill_factor=1.0,
                             noise_sigma=0.01, rng=np.random.default_rng(3))
    np.testing.assert_array_equal(r1, r2)
