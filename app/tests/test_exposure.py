"""Auto-exposure brightness swing: detection, correction, and its cost.

The scan's real enemy isn't random noise, it's auto-exposure re-metering
between frames -- each frame picks up an unknown gain, which breaks the PSA's
constant-brightness assumption and ripples the height map. These tests prove the
pipeline (1) measures an injected swing, (2) corrects it back toward the noise
floor, (3) leaves a clean stack untouched, and (4) recovers a known per-frame
gain. All run through the simulation backend / sim modules -- no hardware.
"""
from __future__ import annotations

import numpy as np
import pytest

from backend import SimulationBackend


@pytest.fixture
def sim(tmp_path, monkeypatch):
    monkeypatch.setenv("MP_OUT_DIR", str(tmp_path))
    return SimulationBackend()


def test_swing_is_measured(sim):
    for injected_pct in (2.0, 5.0):
        m = sim.estimate_noise("bump", injected_sigma_dn=1.0, gain_swing_pct=injected_pct).metrics
        # the measured swing tracks the injected one (a little high: the
        # estimator also sees a touch of the noise/fringe)
        assert injected_pct * 0.6 < m["brightness_swing_pct"] < injected_pct * 1.6


def test_correction_recovers_accuracy(sim):
    m = sim.estimate_noise("bump", injected_sigma_dn=1.0, gain_swing_pct=5.0).metrics
    # a 5% swing wrecks the raw reconstruction; correcting it recovers most of it
    assert m["rmse_raw_mm"] > 3.0 * m["rmse_corrected_mm"]


def test_correction_harmless_without_swing(sim):
    m = sim.estimate_noise("bump", injected_sigma_dn=3.0, gain_swing_pct=0.0).metrics
    assert m["brightness_swing_pct"] < 0.5
    # with no swing to correct, raw and corrected reconstructions agree
    assert m["rmse_corrected_mm"] == pytest.approx(m["rmse_raw_mm"], rel=0.05)


def test_reconstruct_reports_and_corrects_swing(sim):
    # A swung stack reconstructs better with gain normalization on (the default).
    noise = sim._load_sim_noise()
    rec = sim._load_sim_reconstruct()
    stack = sim.capture_dir("bump")
    noise.synth_noisy_stack(stack, "bump", n_periods=8, n_steps=8, sigma=0.0, gain_swing=0.05)

    raw = rec.run(stack, stack.parent / "raw", surface="bump", normalize_gains=False, verbose=False)
    corr = rec.run(stack, stack.parent / "corr", surface="bump", normalize_gains=True, verbose=False)
    assert raw["brightness_swing_pct"] > 2.0  # the swing is reported
    assert corr["rmse"] < raw["rmse"]  # correcting it helps


def test_frame_gains_recovered(sim):
    # Build a stack with a known per-frame gain and check exposure.frame_gains.
    sim._load_sim_noise()  # puts simulation/ on sys.path
    import exposure

    rng = np.random.default_rng(0)
    base = rng.uniform(0.2, 0.8, size=(64, 80))
    true_gains = np.array([0.9, 1.0, 1.1, 1.05, 0.95, 1.0, 0.98, 1.02])
    stack = np.stack([g * base for g in true_gains])
    est = exposure.frame_gains(stack)
    expected = true_gains / true_gains.mean()
    assert np.allclose(est, expected, atol=1e-6)
