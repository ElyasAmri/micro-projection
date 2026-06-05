"""Reload-verify test for the Stage 6 B.4.2b B.3a reference artifact.

The committed reference (config JSON + numbers/array .npz) is the Stage 7
hardware-phase validation target. This test RELOADS the committed config,
re-derives the headline from it via the SAME core path the generator used
(`scripts/build_b4_reference.py` imports `derive_b3a_headline` from here — one
source, no drift), then compares against the committed .npz:

- integer ratios (decoupling, error_ratio) — EXACT (==), pinned as the :.0f
  display mirror so cross-machine BLAS ULP drift can't flip them;
- std_err, max_abs, recovered array — within atol 1e-8 (the regression_data.npz
  tolerance tier; recovered float arrays route through polyfit/lstsq → BLAS).

Intent: the artifact is generated ONCE by the script and committed; this test
NEVER regenerates it. Re-deriving via the live core guards that a future core
change which shifts the B.3a headline is caught here — that is the point.

`conftest.py` puts `src/` on sys.path; the two lines below also add the repo
root (harmless; kept parallel to the other GUI-touching tests). This test itself
imports only CORE (the config carries every param), so no gui import is needed.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import numpy as np
import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for _p in (_ROOT, os.path.join(_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from calibration import fit_tilt_plane  # noqa: E402
from io_utils import ShowcaseConfig, load_config  # noqa: E402
from pipeline import run_inverse_fpp  # noqa: E402
from showcase_metrics import steep_region_ratios  # noqa: E402
from test_surfaces import make_demo_defect, make_steep_dome  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "b4_reference"
CONFIG_PATH = FIXTURE_DIR / "b3a_reference_config.json"
NPZ_PATH = FIXTURE_DIR / "b3a_reference.npz"


def derive_b3a_headline(config: ShowcaseConfig) -> dict:
    """Re-derive the B.3a headline from a ShowcaseConfig — the single source the
    generator and this test both use (GUI-free, all core).

    Returns the frozen quantities: the two integer ratios (the :.0f display
    mirror), the float std_err / max_abs, and the recovered surface array. The
    noise factory builds a FRESH ``default_rng(seed)`` per call, so every
    producer sees identical independent draws regardless of call order — the
    same fresh-per-call semantics the GUI uses.
    """
    golden = make_steep_dome(
        config.surface_shape, config.pixel_size_mm,
        amplitude_px=config.surface_amplitude_px,
        sigma_px=config.surface_sigma_px,
    )
    defect = make_demo_defect(
        config.surface_shape,
        amplitude=config.defect_amplitude_px,
        sigma_px=config.defect_sigma_px,
    )
    part = golden + defect
    geometry = config.to_geometry()
    n = config.n_psi_steps
    deltas = [2.0 * math.pi * k / n for k in range(n)]

    def nk() -> dict:
        if config.noise_on:
            return {"noise_sigma": config.noise_sigma,
                    "rng": np.random.default_rng(config.noise_seed)}
        return {}

    # Headline ratios (golden-vs-golden, matching shape — independent of defect).
    ratios = steep_region_ratios(
        golden, geometry, deltas, nk, with_error_ratio=True
    )
    assert ratios["error_ratio"] is not None and math.isfinite(
        ratios["error_ratio"]
    ), "B.3a reference: error_ratio must be finite"
    decoupling_int = int(format(ratios["decoupling"], ".0f"))
    error_ratio_int = int(format(ratios["error_ratio"], ".0f"))

    # Recovered surface (defect-on) + its error stats — the _recover_part_surface
    # inverse dispatch, then error = recovered - golden (heightmap = golden).
    dev = run_inverse_fpp(
        golden, part, geometry, deltas, selfcal_fit=fit_tilt_plane, **nk(),
    )
    recovered = golden + (dev - dev.mean())
    error = recovered - golden
    std_err = float(np.nanstd(error))
    max_abs = float(np.nanmax(np.abs(error)))

    return {
        "decoupling_int": decoupling_int,
        "error_ratio_int": error_ratio_int,
        "std_err": std_err,
        "max_abs": max_abs,
        "recovered": recovered,
    }


def _load_frozen() -> dict:
    if not NPZ_PATH.exists():
        pytest.fail(
            f"B.4 reference fixture missing: {NPZ_PATH}\n"
            f"Generate it (once) via:\n"
            f"    python scripts/build_b4_reference.py"
        )
    with np.load(NPZ_PATH) as data:
        return {k: data[k].copy() for k in data.files}


@pytest.fixture(scope="module")
def reloaded_config() -> ShowcaseConfig:
    if not CONFIG_PATH.exists():
        pytest.fail(
            f"B.4 reference config missing: {CONFIG_PATH}\n"
            f"Generate it (once) via:\n"
            f"    python scripts/build_b4_reference.py"
        )
    return load_config(CONFIG_PATH)


@pytest.fixture(scope="module")
def derived(reloaded_config) -> dict:
    return derive_b3a_headline(reloaded_config)


@pytest.fixture(scope="module")
def frozen() -> dict:
    return _load_frozen()


def test_integer_ratios_match_exactly(derived, frozen):
    """decoupling and error_ratio re-derive to the SAME displayed integers."""
    assert int(frozen["decoupling_int"]) == derived["decoupling_int"]
    assert int(frozen["error_ratio_int"]) == derived["error_ratio_int"]


def test_scalar_floats_within_tolerance(derived, frozen):
    """std_err and max_abs match within atol 1e-8 (BLAS tolerance tier)."""
    np.testing.assert_allclose(
        derived["std_err"], float(frozen["std_err"]), atol=1e-8,
    )
    np.testing.assert_allclose(
        derived["max_abs"], float(frozen["max_abs"]), atol=1e-8,
    )


def test_recovered_array_within_tolerance(derived, frozen):
    """The recovered surface re-derives to within atol 1e-8 per pixel."""
    assert derived["recovered"].shape == frozen["recovered"].shape
    assert derived["recovered"].dtype == frozen["recovered"].dtype == np.float64
    np.testing.assert_allclose(
        derived["recovered"], frozen["recovered"], atol=1e-8,
    )
