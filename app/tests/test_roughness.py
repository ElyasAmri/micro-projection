"""Roughness measurement -- the end goal: form removal + areal Sa/Sq/Sz.

The multi-frequency ladder resolves a fine texture riding on a large form; these
tests prove the last step turns that height map into a roughness number. They
cover the ISO-25178 Gaussian high-pass in isolation (it passes a fine sinusoid
and removes a broad form), the full recovery of a known texture's Sa/Sq, the
noise-floor bias correction, and -- the whole point of the ladder -- that a
single coarse frequency's noise floor swamps the roughness the ladder resolves.
All run through the sim modules: synthetic forward-model stacks, no hardware.
"""
from __future__ import annotations

import numpy as np
import pytest

from backend import SimulationBackend


@pytest.fixture
def sim(tmp_path, monkeypatch):
    monkeypatch.setenv("MP_OUT_DIR", str(tmp_path))
    return SimulationBackend()


def _build_rough_ladder(noise, root, ladder, sigma=0.0, shape=(512, 640)):
    dirs = []
    for i, n in enumerate(ladder):
        d = root / f"f{i}"
        noise.synth_noisy_stack(d, "rough", n_periods=n, n_steps=8,
                                sigma=sigma, shape=shape, seed=i + 1)
        dirs.append(d)
    return dirs


# -- the Gaussian high-pass in isolation --------------------------------------

def test_gaussian_highpass_passes_a_fine_sinusoid(sim):
    roughness = _load(sim, "roughness")
    # 0.1mm pixels, a 4mm-wavelength cosine of 20um amplitude, cutoff 10mm.
    ny, nx = 200, 200
    xs = (np.arange(nx) * 0.1)[None, :]
    height = (20e-3) * np.cos(2 * np.pi * xs / 4.0) * np.ones((ny, 1))
    valid = np.ones((ny, nx), bool)
    rough, form = roughness.gaussian_highpass(height, valid, 0.1, 0.1, cutoff_mm=10.0)
    p = roughness.areal_parameters(rough, valid)
    # A cosine of amplitude A has Sq = A/sqrt(2); the 4mm wave is well below the
    # 10mm cutoff, so it passes essentially untouched.
    assert p["Sq_um"] == pytest.approx(20.0 / np.sqrt(2.0), rel=0.05)


def test_gaussian_highpass_removes_a_broad_form(sim):
    roughness = _load(sim, "roughness")
    ny, nx = 300, 300
    xs = (np.arange(nx) * 0.1 - 15.0)[None, :]
    ys = (np.arange(ny) * 0.1 - 15.0)[:, None]
    form = 1.0 * np.exp(-(xs ** 2 + ys ** 2) / (2.0 * 25.0 ** 2))  # 1mm, sigma 25mm
    valid = np.ones((ny, nx), bool)
    rough, _ = roughness.gaussian_highpass(form, valid, 0.1, 0.1, cutoff_mm=10.0)
    p = roughness.areal_parameters(rough, valid)
    # The form (>> 10mm cutoff) is almost entirely removed: residual Sq is a
    # tiny fraction of the 1000um form amplitude.
    assert p["Sq_um"] < 5.0


# -- full roughness recovery through the ladder -------------------------------

def test_roughness_recovers_ground_truth(sim, tmp_path):
    noise = sim._load_sim_noise()
    roughness = _load(sim, "roughness")
    ladder = sim.capture_ladder()
    dirs = _build_rough_ladder(noise, tmp_path, ladder, sigma=0.0)

    m = roughness.run(dirs, tmp_path / "out", surface="rough", cutoff_mm=10.0, verbose=False)
    # Clean forward model -> the recovered areal parameters match the exact
    # texture (same filter applied to both).
    assert abs(m["Sa_err_um"]) < 1.0
    assert abs(m["Sq_err_um"]) < 1.0
    assert m["Sq_true_um"] > 10.0  # the specimen actually has roughness to find


def test_roughness_denoise_recovers_true_sq(sim, tmp_path):
    noise = sim._load_sim_noise()
    roughness = _load(sim, "roughness")
    ladder = sim.capture_ladder()
    dirs = _build_rough_ladder(noise, tmp_path, ladder, sigma=5.0 / 255.0)

    m = roughness.run(dirs, tmp_path / "out", surface="rough", cutoff_mm=10.0, verbose=False)
    # Noise inflates the raw Sq; the quadrature correction brings it back to the
    # true value, and the floor/SNR are reported.
    assert m["noise_floor_um"] > 0.5
    assert m["Sq_um"] > m["Sq_denoised_um"]  # raw is inflated by noise
    assert m["Sq_denoised_um"] == pytest.approx(m["Sq_true_um"], abs=1.5)
    assert m["roughness_snr"] > 2.0


def test_ladder_beats_a_single_frequency_for_roughness(sim, tmp_path):
    noise = sim._load_sim_noise()
    roughness = _load(sim, "roughness")
    rec = sim._load_sim_reconstruct()
    ladder = sim.capture_ladder()
    dirs = _build_rough_ladder(noise, tmp_path, ladder, sigma=2.0 / 255.0)

    full = roughness.run(dirs, tmp_path / "ladder", surface="rough", cutoff_mm=10.0, verbose=False)

    # Reconstruct the coarse rung alone and measure its roughness the same way.
    rec.run(dirs[0], tmp_path / "coarse", n_periods=ladder[0], surface="rough", verbose=False)
    hc = np.load(tmp_path / "coarse" / "height.npy")
    vc = np.load(tmp_path / "coarse" / "valid.npy")
    dx, dy = _pixel_pitch(rec, hc.shape)
    rough_c, _ = roughness.gaussian_highpass(hc, vc, dx, dy, cutoff_mm=10.0)
    coarse_sq = roughness.areal_parameters(rough_c, vc)["Sq_um"]

    true_sq = full["Sq_true_um"]
    # The ladder tracks the true roughness; the coarse rung's ~10x larger height
    # noise floods the fine texture, badly inflating its Sq.
    assert abs(full["Sq_um"] - true_sq) < 2.0
    assert coarse_sq > full["Sq_um"] + 4.0


# -- backend: measure off an existing reconstruction --------------------------

def test_backend_measure_roughness_off_reconstruction(sim):
    # Lay a ladder into the default rung dirs, reconstruct, then measure roughness
    # straight off the written height.npy (no re-reconstruction).
    noise = sim._load_sim_noise()
    ladder = sim.capture_ladder()
    dirs = sim.multifreq_capture_dirs("rough", len(ladder))
    for d, n in zip(dirs, ladder):
        noise.synth_noisy_stack(d, "rough", n_periods=n, n_steps=8,
                                sigma=3.0 / 255.0, shape=(512, 640), seed=int(n))
    sim.reconstruct_multifreq("rough")  # writes height.npy / valid.npy

    result = sim.measure_roughness("rough", fine_capture_dir=dirs[-1], fine_n_periods=ladder[-1])
    m = result.metrics
    assert result.roughness_png.exists()
    assert m["Sq_denoised_um"] == pytest.approx(m["Sq_true_um"], abs=1.5)
    assert m["noise_floor_um"] > 0.5 and m["roughness_snr"] > 2.0


def test_backend_measure_roughness_needs_a_reconstruction(sim):
    with pytest.raises(FileNotFoundError):
        sim.measure_roughness("rough")  # nothing reconstructed yet


# -- helpers ------------------------------------------------------------------

def _load(sim, name):
    sim._load_sim_reconstruct()  # ensures simulation/ is on sys.path
    import importlib
    return importlib.import_module(name)


def _pixel_pitch(rec, shape):
    wx, wy = rec.pixel_to_world(shape, 38.7)
    return float(abs(wx[0, 1] - wx[0, 0])), float(abs(wy[1, 0] - wy[0, 0]))
