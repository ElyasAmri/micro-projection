"""Unit tests for src/test_surfaces.py — heightmap generator library.

All surfaces are closed-form analytical, so ATOL_ANALYTICAL = 1e-12 is
used throughout. No regression fixture needed.

Group layout
------------
A. Shape / dtype / finite (parametrized over all 5 generators).
B. make_flat:     all zeros, multiple shapes.
C. make_tilt:     zero slopes -> flat, mean=0 on centered grid, sign,
                  linear superposition.
D. make_gaussian: peak at exact center (odd shape), x/y symmetry,
                  corner < center, amplitude=0 -> flat.
E. make_step:     two unique values, deliberate x-asymmetry, even split
                  at edge=0 when W even, negative height respected.
F. make_sphere:   peak at exact center (odd shape), edge ~= 0, outside
                  exactly 0, x/y symmetry, ValueError guards.
G. Launch-default contract (parametrized over all 5 generators): GUI's
   (480, 640) at 0.1 mm/px returns finite float64.

Even-vs-odd shape note
----------------------
Peak-at-center tests use odd shapes so the geometric center sits on a
pixel exactly. Even shapes put the center between pixels, which would
fail at ATOL_ANALYTICAL by O(pixel_size**2 / sigma**2). Shape/dtype/
finite tests use the GUI's (480, 640) launch defaults.
"""
from __future__ import annotations

import numpy as np
import pytest

from conftest import ATOL_ANALYTICAL
from test_surfaces import (
    make_flat,
    make_gaussian,
    make_sphere,
    make_step,
    make_tilt,
)


ALL_GENERATORS = [make_flat, make_tilt, make_gaussian, make_step, make_sphere]
GENERATOR_IDS = ["flat", "tilt", "gaussian", "step", "sphere"]


# ---------------------------------------------------------------------------
# Group A — Shape / dtype / finite, parametrized over all generators.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fn", ALL_GENERATORS, ids=GENERATOR_IDS)
def test_shape_dtype_finite(fn):
    shape = (480, 640)
    out = fn(shape, 0.1)
    assert out.shape == shape, f"{fn.__name__} returned shape {out.shape}"
    assert out.dtype == np.float64, f"{fn.__name__} returned dtype {out.dtype}"
    assert np.all(np.isfinite(out)), f"{fn.__name__} produced non-finite values"


# ---------------------------------------------------------------------------
# Group B — make_flat
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("shape", [(480, 640), (100, 100), (33, 17)])
def test_make_flat_is_all_zeros(shape):
    out = make_flat(shape, 0.1)
    np.testing.assert_array_equal(
        out, np.zeros(shape, dtype=np.float64),
        err_msg=f"make_flat must be exact zeros at shape {shape}",
    )


# ---------------------------------------------------------------------------
# Group C — make_tilt
# ---------------------------------------------------------------------------
def test_make_tilt_zero_slopes_equals_flat():
    shape = (100, 120)
    ps = 0.1
    np.testing.assert_array_equal(
        make_tilt(shape, ps, slope_x=0.0, slope_y=0.0),
        make_flat(shape, ps),
        err_msg="make_tilt with zero slopes must equal make_flat",
    )


def test_make_tilt_centered_grid_has_mean_zero():
    """Centered grid -> X.mean() == 0 -> tilt has mean 0."""
    shape = (100, 120)
    out = make_tilt(shape, 0.1, slope_x=0.5, slope_y=-0.3)
    np.testing.assert_allclose(
        out.mean(), 0.0, atol=ATOL_ANALYTICAL,
        err_msg="centered tilt must have mean 0 to ATOL_ANALYTICAL",
    )


def test_make_tilt_sign_on_x_axis():
    """slope_x > 0 -> right edge > left edge."""
    shape = (100, 200)
    out = make_tilt(shape, 0.1, slope_x=0.3)
    left_col = out[:, 0]
    right_col = out[:, -1]
    assert np.all(right_col > left_col), (
        "slope_x > 0 must produce higher values on the +X edge"
    )


def test_make_tilt_linear_superposition():
    """make_tilt(a, b) == make_tilt(a, 0) + make_tilt(0, b)."""
    shape = (100, 120)
    ps = 0.1
    combined = make_tilt(shape, ps, slope_x=0.7, slope_y=-0.4)
    x_only = make_tilt(shape, ps, slope_x=0.7, slope_y=0.0)
    y_only = make_tilt(shape, ps, slope_x=0.0, slope_y=-0.4)
    np.testing.assert_allclose(
        combined, x_only + y_only, atol=ATOL_ANALYTICAL,
        err_msg="make_tilt must superpose linearly in slope_x, slope_y",
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
# Group E — make_step
# ---------------------------------------------------------------------------
def test_make_step_two_unique_values():
    out = make_step((100, 120), 0.1, height_mm=0.5, edge_x_mm=0.0)
    unique = np.unique(out)
    assert unique.size == 2, f"expected 2 unique values, got {unique}"
    np.testing.assert_array_equal(unique, np.array([0.0, 0.5]))


def test_make_step_not_symmetric_under_x_flip():
    """Step is deliberately asymmetric: +X side raised, -X side flat.

    Flipping x swaps the two halves. The result must NOT match the
    original.
    """
    out = make_step((100, 120), 0.1, height_mm=0.5, edge_x_mm=0.0)
    flipped = out[:, ::-1]
    assert not np.allclose(out, flipped), (
        "make_step must not be symmetric under x -> -x"
    )


def test_make_step_equal_area_split_when_w_even():
    """edge_x_mm=0 with W even splits the grid into equal halves."""
    H, W = 100, 200
    out = make_step((H, W), 0.1, height_mm=0.5, edge_x_mm=0.0)
    nonzero = np.count_nonzero(out)
    assert nonzero == H * (W // 2), (
        f"expected {H * (W // 2)} raised pixels, got {nonzero}"
    )


def test_make_step_negative_height():
    out = make_step((100, 120), 0.1, height_mm=-0.3, edge_x_mm=0.0)
    unique = np.unique(out)
    np.testing.assert_array_equal(unique, np.array([-0.3, 0.0]))


# ---------------------------------------------------------------------------
# Group F — make_sphere
# ---------------------------------------------------------------------------
def test_make_sphere_peak_at_center_odd_shape():
    shape = (101, 121)
    H, W = shape
    out = make_sphere(shape, 0.1, cap_height_mm=0.5, footprint_radius_mm=20.0)
    np.testing.assert_allclose(
        out[H // 2, W // 2], 0.5, atol=ATOL_ANALYTICAL,
        err_msg="sphere peak at center must equal cap_height_mm",
    )


def test_make_sphere_footprint_edge_approximately_zero():
    """At r exactly equal to footprint_radius_mm, z = 0 analytically.

    We pick a grid where a pixel sits exactly at (a, 0) by choosing
    pixel_size_mm so that footprint_radius_mm is an integer multiple
    of pixel_size_mm.
    """
    shape = (101, 401)  # W=401 -> center at col 200; need col 400 at x = +20.0
    pixel_size_mm = 0.1  # column 400 is 200 px from center -> x = +20.0 mm
    out = make_sphere(
        shape, pixel_size_mm, cap_height_mm=0.5, footprint_radius_mm=20.0
    )
    H, W = shape
    edge_value = out[H // 2, W - 1]
    np.testing.assert_allclose(
        edge_value, 0.0, atol=ATOL_ANALYTICAL,
        err_msg="z at footprint edge (r == a) must be ~ 0",
    )


def test_make_sphere_outside_footprint_exactly_zero():
    """Pixels with r > footprint_radius_mm are exactly 0 by construction."""
    shape = (200, 200)
    out = make_sphere(
        shape, 0.5, cap_height_mm=0.5, footprint_radius_mm=10.0
    )
    # Corner pixel at distance ~ sqrt(2)*50*0.5 = ~35 mm > 10 mm.
    assert out[0, 0] == 0.0
    assert out[-1, -1] == 0.0


def test_make_sphere_symmetric_under_x_flip():
    shape = (101, 121)
    out = make_sphere(shape, 0.1)
    np.testing.assert_allclose(
        out, out[:, ::-1], atol=ATOL_ANALYTICAL,
        err_msg="sphere must be symmetric under x -> -x",
    )


def test_make_sphere_symmetric_under_y_flip():
    shape = (101, 121)
    out = make_sphere(shape, 0.1)
    np.testing.assert_allclose(
        out, out[::-1, :], atol=ATOL_ANALYTICAL,
        err_msg="sphere must be symmetric under y -> -y",
    )


def test_make_sphere_raises_on_nonpositive_cap_height():
    with pytest.raises(ValueError, match="cap_height_mm"):
        make_sphere((100, 100), 0.1, cap_height_mm=0.0)
    with pytest.raises(ValueError, match="cap_height_mm"):
        make_sphere((100, 100), 0.1, cap_height_mm=-0.5)


def test_make_sphere_raises_on_nonpositive_footprint():
    with pytest.raises(ValueError, match="footprint_radius_mm"):
        make_sphere((100, 100), 0.1, footprint_radius_mm=0.0)
    with pytest.raises(ValueError, match="footprint_radius_mm"):
        make_sphere((100, 100), 0.1, footprint_radius_mm=-5.0)


# ---------------------------------------------------------------------------
# Group G — Launch-default contract.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fn", ALL_GENERATORS, ids=GENERATOR_IDS)
def test_launch_defaults_return_finite_canonical_shape(fn):
    """GUI launch contract: shape=(480, 640), pixel_size_mm=0.1 works.

    Same as Group A but called out explicitly because this is the
    GUI's startup signature.
    """
    out = fn((480, 640), 0.1)
    assert out.shape == (480, 640)
    assert out.dtype == np.float64
    assert np.all(np.isfinite(out))
