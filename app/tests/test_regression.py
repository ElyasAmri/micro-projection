"""Frozen-fixture regression tests for the DSP core.

Each test re-runs one pipeline stage on the inputs frozen in
regression_data.npz and compares against that build's golden output, with
tolerances tiered by how the stage computes (methodology from the
fringe-projection-3d suite):

* ATOL_ANALYTICAL (1e-12) -- closed-form array math; any drift is a real
  change, not float noise.
* ATOL_PIPELINE (1e-8) -- arctan2 / unwrap chains: transcendental but
  deterministic on frozen inputs.
* ATOL_FILTERED (1e-6) -- cv2-backed filtering, whose kernel internals may
  legitimately vary a hair across OpenCV builds.

A failure here means the numbers CHANGED -- code, dependency, or geometry
constant. If the change was intentional, rebuild and commit the fixture:

    .venv/bin/python app/tests/build_regression_fixture.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "simulation"))

import occlusion  # noqa: E402
import reconstruct  # noqa: E402
import roughness  # noqa: E402

ATOL_ANALYTICAL = 1e-12
ATOL_PIPELINE = 1e-8
ATOL_FILTERED = 1e-6

FIXTURE = Path(__file__).resolve().parent / "regression_data.npz"


@pytest.fixture(scope="module")
def fx():
    return np.load(FIXTURE)


def _rungs(fx):
    return [f"n{n:g}" for n in fx["ladder"]]


def test_world_grid(fx):
    wx, wy = reconstruct.pixel_to_world(fx["world_x"].shape, float(fx["theta_deg"]))
    np.testing.assert_allclose(wx, fx["world_x"], atol=ATOL_ANALYTICAL)
    np.testing.assert_allclose(wy, fx["world_y"], atol=ATOL_ANALYTICAL)


def test_pixel_pitch_and_lambdas(fx):
    dx, dy = reconstruct.pixel_pitch_mm(fx["world_x"].shape, float(fx["theta_deg"]))
    np.testing.assert_allclose([dx, dy], fx["pixel_pitch"], atol=ATOL_ANALYTICAL)
    for n, tag in zip(fx["ladder"], _rungs(fx)):
        lam = reconstruct.equivalent_wavelength_mm(float(n), float(fx["theta_deg"]))
        np.testing.assert_allclose(lam, fx[f"lambda_{tag}"], atol=ATOL_ANALYTICAL)


def test_carrier_phase(fx):
    for n, tag in zip(fx["ladder"], _rungs(fx)):
        carrier = reconstruct.carrier_phase(fx["world_x"], float(n))
        np.testing.assert_allclose(carrier, fx[f"carrier_{tag}"],
                                   atol=ATOL_ANALYTICAL)


def test_wrap_to_pi(fx):
    np.testing.assert_allclose(reconstruct.wrap_to_pi(fx["wrap_in"]),
                               fx["wrap_out"], atol=ATOL_ANALYTICAL)


def test_psi_from_frames(fx):
    for n, tag in zip(fx["ladder"], _rungs(fx)):
        psi, mod = reconstruct.psi_from_frames(fx[f"frames_{tag}"], float(n),
                                               fx["world_x"])
        np.testing.assert_allclose(psi, fx[f"psi_{tag}"], atol=ATOL_PIPELINE)
        np.testing.assert_allclose(mod, fx[f"mod_{tag}"], atol=ATOL_PIPELINE)


def test_unwrap_multifreq(fx):
    psis = [fx[f"psi_{tag}"] for tag in _rungs(fx)]
    lambdas = [float(fx[f"lambda_{tag}"]) for tag in _rungs(fx)]
    height = reconstruct.unwrap_multifreq(psis, lambdas)
    np.testing.assert_allclose(height, fx["height_multifreq"],
                               atol=ATOL_PIPELINE)


def test_gaussian_highpass_and_areal(fx):
    valid = np.ones(fx["height_multifreq"].shape, dtype=bool)
    dx, dy = fx["pixel_pitch"]
    rough, form = roughness.gaussian_highpass(fx["height_multifreq"], valid,
                                              dx, dy, float(fx["cutoff_mm"]))
    np.testing.assert_allclose(rough, fx["rough"], atol=ATOL_FILTERED)
    np.testing.assert_allclose(form, fx["form"], atol=ATOL_FILTERED)
    params = roughness.areal_parameters(rough, valid)
    expected = dict(zip(fx["areal_keys"].tolist(), fx["areal_values"]))
    for key, value in expected.items():
        np.testing.assert_allclose(params[key], value, atol=ATOL_FILTERED,
                                   err_msg=key)


def test_shadow_mask(fx):
    hidden = occlusion.camera_hidden_mask(fx["height_true"], fx["world_x"],
                                          float(fx["pixel_pitch"][0]))
    assert np.array_equal(hidden, fx["hidden"])


def test_recovery_quality_bar(fx):
    """The recorded end-to-end bar: the multifreq height recovered from the
    synthetic stacks must sit within 50um rms of the true surface. Guards the
    *quality* of the whole chain, not just its byte-stability."""
    rms = float(np.sqrt(np.mean((fx["height_multifreq"] - fx["height_true"]) ** 2)))
    assert rms < 0.050, f"height rms vs truth {rms * 1000:.1f} um"
