"""Unit tests for src/test_surfaces.py — heightmap generator library.

All surfaces are closed-form analytical, so ATOL_ANALYTICAL = 1e-12 is
used throughout. No regression fixture needed.

Group layout
------------
A. Shape / dtype / finite (parametrized over both generators).
B. make_flat:     all zeros, multiple shapes.
D. make_gaussian: peak at exact center (odd shape), x/y symmetry,
                  corner < center, amplitude=0 -> flat.
G. Launch-default contract (parametrized over both generators): GUI's
   (550, 680) at 0.1 mm/px returns finite float64.

(Groups C/E/F — make_tilt / make_step / make_sphere — were removed in
Stage 4c sub-task 1 along with those generators.)

Even-vs-odd shape note
----------------------
Peak-at-center tests use odd shapes so the geometric center sits on a
pixel exactly. Even shapes put the center between pixels, which would
fail at ATOL_ANALYTICAL by O(pixel_size**2 / sigma**2). Shape/dtype/
finite tests use the GUI's (550, 680) launch defaults.
"""
from __future__ import annotations

import numpy as np
import pytest

from conftest import ATOL_ANALYTICAL
from test_surfaces import (
    make_flat,
    make_gaussian,
)


ALL_GENERATORS = [make_flat, make_gaussian]
GENERATOR_IDS = ["flat", "gaussian"]


# ---------------------------------------------------------------------------
# Group A — Shape / dtype / finite, parametrized over all generators.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fn", ALL_GENERATORS, ids=GENERATOR_IDS)
def test_shape_dtype_finite(fn):
    shape = (550, 680)
    out = fn(shape, 0.1)
    assert out.shape == shape, f"{fn.__name__} returned shape {out.shape}"
    assert out.dtype == np.float64, f"{fn.__name__} returned dtype {out.dtype}"
    assert np.all(np.isfinite(out)), f"{fn.__name__} produced non-finite values"


# ---------------------------------------------------------------------------
# Group B — make_flat
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("shape", [(550, 680), (100, 100), (33, 17)])
def test_make_flat_is_all_zeros(shape):
    out = make_flat(shape, 0.1)
    np.testing.assert_array_equal(
        out, np.zeros(shape, dtype=np.float64),
        err_msg=f"make_flat must be exact zeros at shape {shape}",
    )


# ---------------------------------------------------------------------------
# Group D — make_gaussian
# ---------------------------------------------------------------------------
def test_make_gaussian_peak_at_center_odd_shape():
    """Odd-shape grid puts a pixel exactly at (0,0); peak == amplitude_mm.

    Even-shape grids would put the center between pixels and the
    discrete peak would be slightly under amplitude_mm by
    O(pixel_size^2 / sigma^2). Use odd shape so the equality is exact.
    """
    shape = (101, 121)
    H, W = shape
    out = make_gaussian(shape, 0.1, amplitude_mm=0.5, sigma_mm=8.0)
    center = out[H // 2, W // 2]
    np.testing.assert_allclose(
        center, 0.5, atol=ATOL_ANALYTICAL,
        err_msg="peak of centered Gaussian must equal amplitude_mm (odd shape)",
    )


def test_make_gaussian_symmetric_under_x_flip():
    shape = (101, 121)
    out = make_gaussian(shape, 0.1)
    np.testing.assert_allclose(
        out, out[:, ::-1], atol=ATOL_ANALYTICAL,
        err_msg="centered Gaussian must be symmetric under x -> -x",
    )


def test_make_gaussian_symmetric_under_y_flip():
    shape = (101, 121)
    out = make_gaussian(shape, 0.1)
    np.testing.assert_allclose(
        out, out[::-1, :], atol=ATOL_ANALYTICAL,
        err_msg="centered Gaussian must be symmetric under y -> -y",
    )


def test_make_gaussian_corner_less_than_center():
    shape = (101, 121)
    out = make_gaussian(shape, 0.1, amplitude_mm=0.5, sigma_mm=8.0)
    assert out[0, 0] < out[shape[0] // 2, shape[1] // 2], (
        "Gaussian must decay from center to corners"
    )


def test_make_gaussian_zero_amplitude_is_flat():
    shape = (100, 120)
    out = make_gaussian(shape, 0.1, amplitude_mm=0.0, sigma_mm=8.0)
    np.testing.assert_array_equal(
        out, np.zeros(shape, dtype=np.float64),
        err_msg="amplitude_mm=0 must produce a flat surface",
    )


# ---------------------------------------------------------------------------
# Group G — Launch-default contract.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fn", ALL_GENERATORS, ids=GENERATOR_IDS)
def test_launch_defaults_return_finite_canonical_shape(fn):
    """GUI launch contract: shape=(550, 680), pixel_size_mm=0.1 works.

    Same as Group A but called out explicitly because this is the
    GUI's startup signature.
    """
    out = fn((550, 680), 0.1)
    assert out.shape == (550, 680)
    assert out.dtype == np.float64
    assert np.all(np.isfinite(out))
