"""The analytic (filter-free) roughness reference: correctness of the dense
texture sampling and its relationship to the ISO-filtered measurement."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "simulation"))

import roughness  # noqa: E402
import surfaces  # noqa: E402


def test_sq_matches_sinusoid_sum():
    # Independent sinusoids: Sq^2 = sum(A_i^2)/2 (cross terms average out over
    # a window much larger than every wavelength).
    ref = roughness.analytic_reference("rough")
    amps = np.array([a for _, _, a, _ in surfaces._ROUGH_TEXTURE])
    expected_sq = np.sqrt((amps ** 2).sum() / 2.0)
    assert abs(ref["Sq_analytic_um"] - expected_sq) / expected_sq < 0.03


def test_grid_convergence():
    coarse = roughness.analytic_reference("rough", samples_per_mm=5.0)
    fine = roughness.analytic_reference("rough", samples_per_mm=15.0)
    for key in ("Sa_analytic_um", "Sq_analytic_um"):
        assert abs(coarse[key] - fine[key]) / fine[key] < 0.01


def test_no_texture_returns_none():
    assert roughness.analytic_reference("bump") is None


def test_filtered_truth_sits_below_analytic():
    # The ISO Gaussian high-pass transmits each texture wavelength at < 1 and
    # admits little form leakage, so filter-on-truth Sa must land below the
    # filter-free analytic Sa but within the transmission band -- if it ever
    # exceeded it materially, form leakage would be contaminating the number.
    ref = roughness.analytic_reference("rough")
    pitch = 0.1  # mm
    from geometry_constants import H0_MM, W0_MM
    x, y = np.meshgrid(np.arange(-W0_MM / 2, W0_MM / 2, pitch),
                       np.arange(-H0_MM / 2, H0_MM / 2, pitch))
    z = surfaces.rough_height_mm(x, y)
    valid = np.ones(z.shape, dtype=bool)
    rough, _ = roughness.gaussian_highpass(z, valid, pitch, pitch, cutoff_mm=10.0)
    filtered = roughness.areal_parameters(rough, valid)
    assert filtered["Sa_um"] < ref["Sa_analytic_um"] * 1.05
    assert filtered["Sa_um"] > ref["Sa_analytic_um"] * 0.60
