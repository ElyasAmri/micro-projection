"""Multi-frequency temporal phase unwrapping -- the roughness path's backbone.

Roughness needs a small equivalent wavelength (fine fringes) for vertical
resolution, but a fine map alone wraps ambiguously on anything taller than
lambda_eq/2. The fix is a coarse->fine ladder: the coarse rung fixes the range,
each finer rung's 2*pi ambiguity is resolved by the running (coarser) estimate.
These tests prove (1) the pure unwrap resolves a height that aliases the fine
rung, (2) the full round-trip beats a single fine frequency and sharpens the
coarse one by ~10x, (3) it keeps the right fringe orders under noise, and
(4) it rejects mis-ordered ladders. All run through the sim modules -- no
hardware, no Blender (synthetic forward-model stacks).
"""
from __future__ import annotations

import numpy as np
import pytest

from backend import SimulationBackend


@pytest.fixture
def sim(tmp_path, monkeypatch):
    monkeypatch.setenv("MP_OUT_DIR", str(tmp_path))
    return SimulationBackend()


def _build_ladder(noise, root, surface, ladder, sigma=0.0, gain_swing=0.0):
    """A per-frequency stack directory for each rung, coarse first."""
    dirs = []
    for i, n in enumerate(ladder):
        d = root / f"f{i}"
        noise.synth_noisy_stack(d, surface, n_periods=n, n_steps=8,
                                sigma=sigma, gain_swing=gain_swing, seed=i + 1)
        dirs.append(d)
    return dirs


def test_unwrap_resolves_a_height_that_aliases_the_fine_rung(sim):
    rec = sim._load_sim_reconstruct()
    lambdas = [rec.equivalent_wavelength_mm(n, 38.7) for n in (8.0, 24.0, 80.0)]
    # Heights inside the coarse range (+/-6.8mm) but well past the fine range
    # (+/-0.68mm), so the finest rung on its own wraps several times.
    h_true = np.array([[0.0, 0.6, 1.5, 3.0, -2.0, -4.5]])
    psis = [rec.wrap_to_pi(2.0 * np.pi * h_true / lam) for lam in lambdas]

    h = rec.unwrap_multifreq(psis, lambdas)
    assert np.allclose(h, h_true, atol=1e-9)

    # The fine rung taken at face value is wrong wherever |h| > lambda_fine/2.
    h_fine_alone = psis[-1] / (2.0 * np.pi) * lambdas[-1]
    assert not np.allclose(h_fine_alone, h_true, atol=1e-3)


def test_run_multifreq_beats_a_single_fine_frequency(sim, tmp_path):
    rec = sim._load_sim_reconstruct()
    noise = sim._load_sim_noise()
    ladder = list(rec.N_PERIODS_LADDER)
    dirs = _build_ladder(noise, tmp_path, "bump", ladder)

    mf = rec.run_multifreq(dirs, tmp_path / "mf", surface="bump", verbose=False)
    fine = rec.run(dirs[-1], tmp_path / "fine", n_periods=ladder[-1], surface="bump", verbose=False)

    # The 3mm bump aliases the finest rung; the ladder unwraps it cleanly.
    assert mf["rmse"] < 0.05
    assert mf["r2"] > 0.999
    assert fine["rmse"] > 10.0 * mf["rmse"]
    # Metrics expose both ends of the ladder.
    assert mf["lambda_eq_mm"] < mf["lambda_eq_coarse_mm"]
    assert mf["unambiguous_range_mm"] == pytest.approx(mf["lambda_eq_coarse_mm"] / 2.0)


def test_multifreq_sharpens_the_coarse_rung(sim, tmp_path):
    rec = sim._load_sim_reconstruct()
    noise = sim._load_sim_noise()
    ladder = list(rec.N_PERIODS_LADDER)
    dirs = _build_ladder(noise, tmp_path, "bump", ladder)

    mf = rec.run_multifreq(dirs, tmp_path / "mf", surface="bump", verbose=False)
    coarse = rec.run(dirs[0], tmp_path / "coarse", n_periods=ladder[0], surface="bump", verbose=False)

    # Finest lambda_eq is ~10x smaller, so the quantization-limited height noise
    # drops with it -- the ladder is markedly sharper than the coarse rung alone.
    assert mf["rmse"] < coarse["rmse"] / 3.0


def test_multifreq_unwrap_holds_orders_under_noise(sim, tmp_path):
    rec = sim._load_sim_reconstruct()
    noise = sim._load_sim_noise()
    ladder = list(rec.N_PERIODS_LADDER)
    dirs = _build_ladder(noise, tmp_path, "bump", ladder, sigma=3.0 / 255.0)

    mf = rec.run_multifreq(dirs, tmp_path / "mf", surface="bump", verbose=False)
    # A single wrong fringe order would blow RMSE up by ~a full lambda_eq (1.4mm);
    # staying at the few-um level proves every order was picked correctly.
    assert mf["rmse"] < 0.05
    assert mf["r2"] > 0.99


def test_run_multifreq_rejects_bad_ladders(sim, tmp_path):
    rec = sim._load_sim_reconstruct()
    a, b = tmp_path / "a", tmp_path / "b"
    with pytest.raises(ValueError):  # fewer than 2 rungs -> use run()
        rec.run_multifreq([a], tmp_path / "o", n_periods_ladder=[8.0])
    with pytest.raises(ValueError):  # dirs vs ladder length mismatch
        rec.run_multifreq([a, b], tmp_path / "o", n_periods_ladder=[8.0])
    with pytest.raises(ValueError):  # not coarse -> fine
        rec.run_multifreq([a, b], tmp_path / "o", n_periods_ladder=[24.0, 8.0])


def test_unwrap_multifreq_rejects_bad_ladders(sim):
    rec = sim._load_sim_reconstruct()
    z = np.zeros((2, 2))
    with pytest.raises(ValueError):  # length mismatch
        rec.unwrap_multifreq([z, z], [1.0])
    with pytest.raises(ValueError):  # lambdas must strictly decrease
        rec.unwrap_multifreq([z, z], [1.0, 2.0])
