"""Tests for the shared heightmap->GLSurfacePlotItem render helper.

`centered_coords` is pure (headless). `apply_heightmap` needs a
GLSurfacePlotItem, so it uses the `qapp` fixture.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from gui.surface_render import apply_heightmap, centered_coords  # noqa: E402


# ---------------------------------------------------------------------------
# centered_coords — pure.
# ---------------------------------------------------------------------------
def test_centered_coords_symmetric_extent():
    x, y = centered_coords((550, 680), 0.1)
    assert len(x) == 680 and len(y) == 550
    assert x[0] == pytest.approx(-(679 / 2) * 0.1)
    assert x[-1] == pytest.approx((679 / 2) * 0.1)
    assert y[0] == pytest.approx(-(549 / 2) * 0.1)
    # Mean is exactly the center (0).
    assert abs(float(x.mean())) < 1e-12
    assert abs(float(y.mean())) < 1e-12


def test_centered_coords_odd_vs_even_length():
    # Odd W -> exact 0 at center.
    x_odd, _ = centered_coords((1, 3), 1.0)
    np.testing.assert_array_equal(x_odd, [-1.0, 0.0, 1.0])
    # Even W -> straddles 0.
    x_even, _ = centered_coords((1, 4), 1.0)
    np.testing.assert_array_equal(x_even, [-1.5, -0.5, 0.5, 1.5])


def test_centered_coords_pixel_scaling():
    x, y = centered_coords((3, 3), 0.5)
    np.testing.assert_array_equal(x, [-0.5, 0.0, 0.5])
    np.testing.assert_array_equal(y, [-0.5, 0.0, 0.5])


# ---------------------------------------------------------------------------
# apply_heightmap — needs a GL item.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_apply_heightmap_transposes_z_and_reshapes_colors(qapp):
    import pyqtgraph.opengl as gl

    item = gl.GLSurfacePlotItem(shader="shaded", smooth=False, drawEdges=False)
    H, W = 4, 6
    hm = np.arange(H * W, dtype=np.float64).reshape(H, W)
    colors = np.zeros((H, W, 4), dtype=np.float32)
    colors[..., 3] = 1.0

    apply_heightmap(item, hm, colors, pixel_size_mm=0.1)

    # z stored transposed to (W, H).
    assert item._z.shape == (W, H)
    np.testing.assert_array_equal(item._z, hm.T)
    # Centered coords applied.
    np.testing.assert_allclose(item._x, (np.arange(W) - (W - 1) / 2) * 0.1)
    np.testing.assert_allclose(item._y, (np.arange(H) - (H - 1) / 2) * 0.1)
    # Colors reshaped to flat (W*H, 4).
    assert item._meshdata._vertexColors.shape == (W * H, 4)


def test_apply_heightmap_applies_z_exaggeration(qapp):
    import pyqtgraph.opengl as gl

    item = gl.GLSurfacePlotItem(shader="shaded", smooth=False, drawEdges=False)
    hm = np.ones((3, 5), dtype=np.float64)
    colors = np.zeros((3, 5, 4), dtype=np.float32)

    apply_heightmap(item, hm, colors, pixel_size_mm=0.1, z_exaggeration=2.0)

    np.testing.assert_array_equal(item._z, (hm * 2.0).T)
