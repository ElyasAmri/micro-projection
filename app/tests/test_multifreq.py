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
from PySide6.QtTest import QTest

from backend import SimulationBackend, create_backend


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


# -- backend integration: reconstruct from the per-rung capture dirs ----------

def test_backend_reconstruct_multifreq_uses_default_rung_dirs(sim):
    # The sim fixture points MP_OUT_DIR at a tmp dir; lay a synthesized ladder
    # into the exact dirs the backend reads by default (out/app/bump/capture_f*).
    noise = sim._load_sim_noise()
    ladder = sim.capture_ladder()
    dirs = sim.multifreq_capture_dirs("bump", len(ladder))
    for d, n in zip(dirs, ladder):
        noise.synth_noisy_stack(d, "bump", n_periods=n, n_steps=8, sigma=0.0)

    result = sim.reconstruct_multifreq("bump")  # no explicit dirs -> the defaults
    m = result.metrics
    assert result.height_png.exists()
    assert result.ground_truth_png.exists()  # known specimen -> scored + gt map
    assert m["n_periods_ladder"] == list(ladder)
    assert m["rmse"] < 0.05 and m["r2"] > 0.999


def test_backend_reconstruct_multifreq_reports_missing_rung(sim):
    noise = sim._load_sim_noise()
    ladder = sim.capture_ladder()
    dirs = sim.multifreq_capture_dirs("bump", len(ladder))
    # populate all but the last rung
    for d, n in zip(dirs[:-1], ladder[:-1]):
        noise.synth_noisy_stack(d, "bump", n_periods=n, n_steps=8, sigma=0.0)
    with pytest.raises(FileNotFoundError):
        sim.reconstruct_multifreq("bump")


# -- UI orchestration: the async coarse->fine ladder state machine ------------

def test_mainwindow_multifreq_pipeline_end_to_end(qapp, tmp_path, monkeypatch):
    """Drive the whole multi-frequency pipeline through MainWindow on the
    hardware backend + synthetic camera (no device, no Blender): it must capture
    every rung into its own capture_f<i> dir, then unwrap them into a height map.
    Covers the _advance_or_reconstruct_ladder sequencing the backend tests skip."""
    monkeypatch.setenv("MP_OUT_DIR", str(tmp_path))
    monkeypatch.setenv("MP_CAMERA", "dummy")
    monkeypatch.setenv("MP_CAPTURE_SETTLE_MS", "1")  # don't wait 200ms/frame in a test
    from ui.main_window import MainWindow

    backend = create_backend("hardware")
    monkeypatch.setattr(backend, "capture_ladder", lambda: [8.0, 24.0])  # short ladder
    win = MainWindow(backend=backend)
    try:
        win._cmd_run_multifreq({"surface": "live"})
        height = tmp_path / "app" / "live" / "height_reconstructed.png"
        for _ in range(3000):  # <= 30s ceiling; breaks as soon as it lands
            done = (win._ladder_i >= len(win._ladder)
                    and not win._capture_runner.is_running()
                    and height.exists())
            if done:
                break
            QTest.qWait(10)

        assert height.exists(), "multi-frequency pipeline did not produce a height map"
        assert win._ladder_i == len(win._ladder)  # both rungs captured, in order
        dirs = backend.multifreq_capture_dirs("live", len(win._ladder))
        for d in dirs:
            assert len(sorted(d.glob("frame_*.png"))) == 8
        # the pipeline chains into roughness off the unwrapped height map
        assert (tmp_path / "app" / "live" / "roughness_map.png").exists()
    finally:
        if hasattr(backend, "shutdown"):
            backend.shutdown()
        win.close()
