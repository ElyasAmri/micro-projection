"""The noise-estimation pipeline.

Proves the three things the pipeline promises: it recovers a *known* injected
noise level, the height error margin it predicts matches the *actual*
reconstruction error on the noisy stack, and the margin scales with the noise.
Runs entirely through the simulation backend (synthetic stacks), so no hardware
or Blender is needed; MP_OUT_DIR is redirected to a tmp dir so nothing touches
the repo's out/.
"""
from __future__ import annotations

import pytest

from backend import NoiseEstimateResult, SimulationBackend


@pytest.fixture
def sim(tmp_path, monkeypatch):
    monkeypatch.setenv("MP_OUT_DIR", str(tmp_path))
    return SimulationBackend()


def test_estimator_recovers_injected_noise(sim):
    for injected_dn in (3.0, 8.0):
        m = sim.estimate_noise("bump", injected_sigma_dn=injected_dn).metrics
        assert m["injected_sigma_dn"] == pytest.approx(injected_dn)
        assert abs(m["sigma_rel_error"]) < 0.08  # recovered within 8%
        assert m["sigma_spatial_dn"] > 0  # independent cross-check reported


def test_predicted_margin_matches_actual_reconstruction_error(sim):
    m = sim.estimate_noise("bump", injected_sigma_dn=6.0).metrics
    assert m["actual_rmse_mm"] is not None
    ratio = m["actual_rmse_mm"] / m["predicted_rmse_mm"]
    assert 0.7 < ratio < 1.4  # the noise margin predicts the real error


def test_outputs_written(sim):
    result = sim.estimate_noise("bump", injected_sigma_dn=5.0)
    assert isinstance(result, NoiseEstimateResult)
    assert result.uncertainty_png.exists()
    assert result.noise_map_png.exists()


def test_margin_scales_with_noise(sim):
    lo = sim.estimate_noise("bump", injected_sigma_dn=2.0).metrics["height_uncertainty_um_mean"]
    hi = sim.estimate_noise("bump", injected_sigma_dn=12.0).metrics["height_uncertainty_um_mean"]
    assert hi > 3.0 * lo  # ~6x the noise -> ~6x the margin (linear propagation)


def test_estimate_reads_an_existing_capture_without_injection(sim):
    # Lay down a capture stack, then estimate its noise with nothing injected
    # (the real-capture path): no injected score, but the estimate is produced.
    noise = sim._load_sim_noise()
    cap = sim.capture_dir("bump")  # out/app/bump/capture under the tmp MP_OUT_DIR
    noise.synth_noisy_stack(cap, "bump", n_periods=8, n_steps=8, sigma=4.0 / 255.0)
    m = sim.estimate_noise("bump", injected_sigma_dn=None).metrics
    assert "injected_sigma_dn" not in m
    assert "sigma_rel_error" not in m
    assert m["sigma_est_dn"] > 0
