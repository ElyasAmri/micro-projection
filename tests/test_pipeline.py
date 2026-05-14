"""Unit tests for src/pipeline.py — run_pipeline() integration entry point.

Scope
-----
Covers the public `run_pipeline()` contract: shape/dtype/finiteness,
default-model behavior, Gaussian recovery against the regression
fixture, n_psi_steps wiring, and geometry-protocol agnosticism.

Internal math (geometry formulas, project() bias model, PSI extract,
unwrap, calibration, reconstruction) is covered by the individual
module tests — not duplicated here.
"""
from __future__ import annotations

import numpy as np
import pytest

from conftest import ATOL_PIPELINE
from geometry import HybridGeometry, SymmetricGeometry
from pipeline import run_pipeline


# ---------------------------------------------------------------------------
# Shape / dtype / finiteness
# ---------------------------------------------------------------------------
def test_run_pipeline_returns_same_shape(regression_data):
    geom = SymmetricGeometry()
    h_in = regression_data["H_obj"]
    recovered = run_pipeline(h_in, geom, n_psi_steps=4)
    assert recovered.shape == h_in.shape


def test_run_pipeline_returns_float64(regression_data):
    geom = SymmetricGeometry()
    h_in = regression_data["H_obj"]
    recovered = run_pipeline(h_in, geom, n_psi_steps=4)
    assert recovered.dtype == np.float64


def test_run_pipeline_returns_finite(regression_data):
    geom = SymmetricGeometry()
    h_in = regression_data["H_obj"]
    recovered = run_pipeline(h_in, geom, n_psi_steps=4)
    assert np.all(np.isfinite(recovered)), "recovered contains NaN/Inf"


# ---------------------------------------------------------------------------
# Model-arg default
# ---------------------------------------------------------------------------
def test_run_pipeline_default_model_is_taylor(regression_data):
    """Default model arg must match explicit 'taylor' bit-for-bit.

    `model` is currently a no-op in the object leg of run_pipeline,
    so both calls produce identical output. This test guards against
    a future refactor that silently changes the default.
    """
    geom = SymmetricGeometry()
    h_in = regression_data["H_obj"]
    r_default = run_pipeline(h_in, geom, n_psi_steps=4)
    r_taylor = run_pipeline(h_in, geom, n_psi_steps=4, model="taylor")
    np.testing.assert_array_equal(
        r_default, r_taylor,
        err_msg="default model arg must match explicit 'taylor'",
    )


# ---------------------------------------------------------------------------
# Recovery against the regression fixture (tight integration check)
# ---------------------------------------------------------------------------
def test_run_pipeline_gaussian_recovery(regression_data):
    """SymmetricGeometry() + fixture H_obj reproduces fixture H_rec0 to ATOL_PIPELINE.

    Compares against the fixture's H_rec0 — the notebook's recovered
    height — not the raw H_obj ground truth. The recovery itself has
    ~1e-5 residual error (notebook BASELINE_STD = 1.76e-5) from the
    tilt-fit step; that's the recovery quality, not a pipeline bug.
    Reproducing H_rec0 element-wise to 1e-8 confirms run_pipeline
    matches the integration test's existing contract bit-for-bit.
    """
    geom = SymmetricGeometry()
    h_in = regression_data["H_obj"]
    recovered = run_pipeline(h_in, geom, n_psi_steps=4)
    np.testing.assert_allclose(
        recovered, regression_data["H_rec0"], atol=ATOL_PIPELINE,
        err_msg=(
            "run_pipeline must reproduce the notebook's H_rec0 fixture "
            "to ATOL_PIPELINE (the input H_obj is recovered only to "
            "~1e-5 because of the self-cal tilt-fit residual)"
        ),
    )


# ---------------------------------------------------------------------------
# n_psi_steps wiring
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("n_psi_steps", [4, 8])
def test_run_pipeline_n_psi_steps_4_and_8(regression_data, n_psi_steps):
    """Both 4-step and 8-step PSI run end-to-end with finite output.

    No absolute comparison: chapter notes both schemes are valid; the
    chapter uses 8-step, the notebook uses 4-step. Test just confirms
    the parameter wires through cleanly.
    """
    geom = SymmetricGeometry()
    h_in = regression_data["H_obj"]
    recovered = run_pipeline(h_in, geom, n_psi_steps=n_psi_steps)
    assert recovered.shape == h_in.shape
    assert np.all(np.isfinite(recovered))


# ---------------------------------------------------------------------------
# Geometry-protocol agnosticism
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# return_stages kwarg (task 4d)
# ---------------------------------------------------------------------------
def test_run_pipeline_return_stages_dict_keys(regression_data):
    """return_stages=True yields (ndarray, dict-with-4-keys)."""
    geom = SymmetricGeometry()
    h_in = regression_data["H_obj"]
    result = run_pipeline(h_in, geom, n_psi_steps=4, return_stages=True)

    assert isinstance(result, tuple) and len(result) == 2, (
        f"return_stages=True must yield a 2-tuple; got {type(result).__name__}"
    )
    recovered, stages = result
    assert isinstance(recovered, np.ndarray)
    assert isinstance(stages, dict)
    expected_keys = {"ground_truth", "fringe_frame", "wrapped_phase", "unwrapped_phase"}
    assert set(stages.keys()) == expected_keys, (
        f"stages dict has {set(stages.keys())}, expected {expected_keys}"
    )


def test_run_pipeline_return_stages_shapes():
    """All stage arrays have the same (H, W) shape as the input."""
    geom = SymmetricGeometry(H=120, W=160)
    rng = np.random.RandomState(0)
    h_in = rng.standard_normal((120, 160)) * 0.01

    recovered, stages = run_pipeline(
        h_in, geom, n_psi_steps=4, return_stages=True
    )
    assert recovered.shape == (120, 160)
    for name, arr in stages.items():
        assert arr.shape == (120, 160), (
            f"stage {name!r} has shape {arr.shape}, expected (120, 160)"
        )


def test_run_pipeline_hybrid_geometry(regression_data):
    """HybridGeometry with fixture-matched params reproduces fixture H_rec0.

    The fixture was generated under SymmetricGeometry (M=1, p=40,
    theta=15 deg, a=2000). Constructing HybridGeometry with the same
    parameters exercises the pipeline through a different geometry
    type. Both classes share the Eq. 2-51 lambda_eq formula post-
    Stage 3.5, so identical constructor args produce identical
    lambda_eq and identical recovery output.
    """
    geom = HybridGeometry(
        M=1.0,
        p=40.0,
        a=2000.0,
        theta_projector=float(np.deg2rad(15.0)),
    )
    h_in = regression_data["H_obj"]
    recovered = run_pipeline(h_in, geom, n_psi_steps=4)
    np.testing.assert_allclose(
        recovered, regression_data["H_rec0"], atol=ATOL_PIPELINE,
        err_msg=(
            "HybridGeometry with fixture-matched params must reproduce "
            "the fixture H_rec0 to ATOL_PIPELINE"
        ),
    )
