"""Unit tests for src/stl_loader.py::load_stl_heightmap_full_scale.

Stage 4d sub-task 2. Synthetic in-memory meshes via tmp_path, no
fixtures on disk — peer of tests/test_stl_loader.py for the
new full-scale rasterization path.

The function's contract: take a part of arbitrary XY size, return a
heightmap sized to fit it at the requested pitch (with `ceil` rounding,
never clipping the part) plus the part-local `(x_min, y_min)` corner.
"""
from __future__ import annotations

import numpy as np
from stl import mesh as stl_mesh

from stl_loader import load_stl_heightmap_full_scale


def _box(cx: float, cy: float, cz: float,
         sx: float, sy: float, sz: float) -> np.ndarray:
    """Closed axis-aligned box (12 triangles) centered at (cx, cy, cz)."""
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    p = {}
    for ix, sxn in ((0, -hx), (1, hx)):
        for iy, syn in ((0, -hy), (1, hy)):
            for iz, szn in ((0, -hz), (1, hz)):
                p[(ix, iy, iz)] = (cx + sxn, cy + syn, cz + szn)

    def quad(a, b, c, d):
        return [[p[a], p[b], p[c]], [p[a], p[c], p[d]]]

    tris = []
    tris += quad((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))  # top
    tris += quad((0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0))  # bottom
    tris += quad((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1))  # y-
    tris += quad((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0))  # y+
    tris += quad((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0))  # x-
    tris += quad((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1))  # x+
    return np.asarray(tris, dtype=np.float64)


def _tilted_slab(width: float, height: float, z_max: float) -> np.ndarray:
    """Two triangles forming an open slab from z=0 at -x edge to z=z_max
    at +x edge. Centered at the origin in XY."""
    hx, hy = width / 2, height / 2
    return np.asarray(
        [
            [(-hx, -hy, 0.0), (hx, -hy, z_max), (hx, hy, z_max)],
            [(-hx, -hy, 0.0), (hx, hy, z_max), (-hx, hy, 0.0)],
        ],
        dtype=np.float64,
    )


def _write_stl(tris: np.ndarray, path) -> str:
    data = np.zeros(len(tris), dtype=stl_mesh.Mesh.dtype)
    m = stl_mesh.Mesh(data, remove_empty_areas=False)
    if len(tris):
        m.vectors[:] = tris
    out = str(path)
    m.save(out)
    return out


# ---------------------------------------------------------------------------
# 1. 100 x 80 mm rectangular slab centered at origin: shape (800, 1000).
# Flat-topped box -> single-height visible envelope -> collapses to z = 0.
# ---------------------------------------------------------------------------
def test_full_scale_box_shape_and_top(tmp_path):
    p = _write_stl(
        _box(0, 0, 0, 100.0, 80.0, 20.0),
        tmp_path / "slab.stl",
    )
    hm, origin = load_stl_heightmap_full_scale(p, 0.1)

    assert hm.shape == (800, 1000), f"got {hm.shape}"
    # The box fills its whole bbox and has a single-height visible top, so
    # lifting by the visible minimum collapses the interior to z = 0.
    H, W = hm.shape
    interior = hm[H // 2 - 50:H // 2 + 50, W // 2 - 50:W // 2 + 50]
    np.testing.assert_allclose(interior, 0.0, atol=1e-9)
    # Origin is the part's (x_min, y_min) = (-50, -40).
    assert origin == (-50.0, -40.0)


# ---------------------------------------------------------------------------
# 2. 200 x 100 mm thin slab. Shape (1000, 2000); flat-topped box ->
# single-height visible envelope -> interior collapses to z = 0.
# ---------------------------------------------------------------------------
def test_full_scale_thin_slab(tmp_path):
    p = _write_stl(
        _box(0, 0, 0, 200.0, 100.0, 0.5),
        tmp_path / "thin.stl",
    )
    hm, origin = load_stl_heightmap_full_scale(p, 0.1)

    assert hm.shape == (1000, 2000)
    # Flat top -> visible envelope is one height -> lift to the visible
    # minimum gives z = 0 across the interior (no relief).
    H, W = hm.shape
    interior = hm[H // 2 - 50:H // 2 + 50, W // 2 - 50:W // 2 + 50]
    np.testing.assert_allclose(interior, 0.0, atol=1e-9)
    assert origin == (-100.0, -50.0)


# ---------------------------------------------------------------------------
# 3. Tilted 150 x 120 mm slab. Finite (non-zero) inside the footprint,
# 0 outside (no triangles cover -> bare stage).
# ---------------------------------------------------------------------------
def test_full_scale_tilted_slab(tmp_path):
    p = _write_stl(
        _tilted_slab(150.0, 120.0, 10.0),
        tmp_path / "tilted.stl",
    )
    hm, origin = load_stl_heightmap_full_scale(p, 0.1)

    # ceil(150 / 0.1) = 1500, ceil(120 / 0.1) = 1200.
    assert hm.shape == (1200, 1500)
    # Interior pixels: non-zero (height grows with x).
    H, W = hm.shape
    interior_strip = hm[H // 2, W // 2 - 100:W // 2 + 100]
    assert np.all(interior_strip > 0.0), "tilted slab interior should be non-zero"
    # The -x edge of the slab is z=0 in the source (after lift, z_min=0 anyway).
    assert hm[H // 2, 5] <= hm[H // 2, W - 5], "z should grow toward +x"


# ---------------------------------------------------------------------------
# 4. Offset cube: 50 x 50 x 10 mm centered at (100, 50). The origin
# returned should match the part's bbox minimum, NOT (0, 0).
# ---------------------------------------------------------------------------
def test_full_scale_offset_origin(tmp_path):
    p = _write_stl(
        _box(100.0, 50.0, 5.0, 50.0, 50.0, 10.0),
        tmp_path / "offset.stl",
    )
    hm, origin = load_stl_heightmap_full_scale(p, 0.1)

    assert hm.shape == (500, 500)
    # Cube bbox: x in [75, 125], y in [25, 75]. Origin = (x_min, y_min).
    assert origin == (75.0, 25.0)


# ---------------------------------------------------------------------------
# 5. Different pixel size: 0.05 mm/px on a 100 x 80 box doubles the shape.
# ---------------------------------------------------------------------------
def test_full_scale_pixel_size_scales_shape(tmp_path):
    p = _write_stl(
        _box(0, 0, 0, 100.0, 80.0, 5.0),
        tmp_path / "box.stl",
    )
    hm, origin = load_stl_heightmap_full_scale(p, 0.05)
    assert hm.shape == (1600, 2000)
    assert origin == (-50.0, -40.0)
