"""Phase-to-height calibration: fitting the per-pixel z<-phase map from known-z
reference planes, and reconstructing through it.

On the ideal (forward-model) geometry the calibration must be a near-identity: it
should recover the nominal sensitivity k = 2*pi/lambda_eq with a ~zero carrier
residual, reconstruct a surface the same as the nominal path, and unwrap a z
sweep that spans more than one fringe. (The payoff on *real* perspective geometry
-- rough-surface form RMSE 134um -> 24um -- is a Blender-camera result, not
runnable headless; see report/math.tex "Geometry calibration".)
"""
from __future__ import annotations

import importlib

import numpy as np
import pytest

from backend import SimulationBackend


@pytest.fixture
def sim(tmp_path, monkeypatch):
    monkeypatch.setenv("MP_OUT_DIR", str(tmp_path))
    return SimulationBackend()


def _load(sim, name):
    sim._load_sim_reconstruct()  # puts simulation/ on sys.path
    return importlib.import_module(name)


def _flat_planes(noise, root, zs, n_periods=80.0, sigma=0.5 / 255.0, shape=(256, 320)):
    dirs = []
    for z in zs:
        d = root / f"z{z:+.2f}"
        noise.synth_noisy_stack(d, "flat", n_periods=n_periods, n_steps=8, sigma=sigma,
                                shape=shape, z_offset_mm=z, seed=int(round(z * 100)) + 1000)
        dirs.append(d)
    return dirs


def test_calibrate_recovers_ideal_geometry(sim, tmp_path):
    noise = sim._load_sim_noise()
    cal = _load(sim, "calibration")
    rec = sim._load_sim_reconstruct()
    zs = [-0.5, -0.25, 0.0, 0.25, 0.5]
    c = cal.calibrate(zs, _flat_planes(noise, tmp_path, zs), n_periods=80.0)

    k_nom = 2 * np.pi / rec.equivalent_wavelength_mm(80.0, 38.7)
    assert np.nanmedian(c.k[c.valid]) == pytest.approx(k_nom, rel=0.01)
    c0_um = (c.c0 / c.k) * 1000.0
    assert np.sqrt(np.nanmean(c0_um[c.valid] ** 2)) < 5.0  # carrier residual ~0 on ideal geometry
    assert c.fit_rms_um < 5.0


def test_calibrate_unwraps_beyond_one_fringe(sim, tmp_path):
    # +/-1mm sweep: psi = k*z reaches ~4.6 rad > pi, so the per-plane phase wraps.
    # The k-guided unwrap must still recover the right slope (np.unwrap would not).
    noise = sim._load_sim_noise()
    cal = _load(sim, "calibration")
    rec = sim._load_sim_reconstruct()
    zs = [-1.0, -0.5, 0.0, 0.5, 1.0]
    c = cal.calibrate(zs, _flat_planes(noise, tmp_path, zs), n_periods=80.0)

    k_nom = 2 * np.pi / rec.equivalent_wavelength_mm(80.0, 38.7)
    assert np.nanmedian(c.k[c.valid]) == pytest.approx(k_nom, rel=0.01)
    assert c.fit_rms_um < 5.0


def test_calibrated_reconstruction_matches_nominal_on_ideal_geometry(sim, tmp_path):
    noise = sim._load_sim_noise()
    cal = _load(sim, "calibration")
    rec = sim._load_sim_reconstruct()
    ladder = sim.capture_ladder()
    shape = (256, 320)

    zs = [-0.5, -0.25, 0.0, 0.25, 0.5]
    cdirs = _flat_planes(noise, tmp_path / "cal", zs, n_periods=ladder[-1], shape=shape)
    c = cal.calibrate(zs, cdirs, n_periods=ladder[-1])

    bdirs = []
    for n in ladder:
        d = tmp_path / "bump" / f"f{int(n)}"
        noise.synth_noisy_stack(d, "bump", n_periods=n, n_steps=8, sigma=0.0, shape=shape, seed=int(n))
        bdirs.append(d)

    nom = rec.run_multifreq(bdirs, tmp_path / "nom", surface="bump", n_periods_ladder=ladder, verbose=False)
    cbr = cal.reconstruct_calibrated(bdirs, tmp_path / "cal_recon", c,
                                     n_periods_ladder=ladder, surface="bump", verbose=False)
    # Identity geometry: the calibrated result tracks the nominal one, both good.
    assert cbr["calibrated"] is True
    assert cbr["rmse"] < nom["rmse"] + 0.01
    assert cbr["rmse"] < 0.05
