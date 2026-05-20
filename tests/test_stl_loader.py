"""Unit tests for src/stl_loader.py — STL -> heightmap loader.

Synthetic meshes are built in memory via numpy-stl's Mesh API and
written to `tmp_path`; no real STL fixtures live in the repo.

Grid sizing rule
----------------
Every test grid is sized so the part's footprint is strictly smaller
than the grid. The uncovered bare-stage margin (value 0) is what pins
`heightmap.min() == 0` honestly — without a margin a part that fills the
grid would have a positive minimum.
"""
from __future__ import annotations

import math

import numpy as np
import pytest
from stl import mesh as stl_mesh

from stl_loader import get_stl_bbox_mm, load_stl_heightmap


# ---------------------------------------------------------------------------
# Synthetic-mesh builders. Each returns an (N, 3, 3) float64 array of
# triangle vertices (last axis = x, y, z in mm).
# ---------------------------------------------------------------------------
def _box(cx: float, cy: float, cz: float,
         sx: float, sy: float, sz: float) -> np.ndarray:
    """Closed axis-aligned box (12 triangles) centered at (cx, cy, cz)."""
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    # 8 corners
    p = {}
    for ix, sxn in ((0, -hx), (1, hx)):
        for iy, syn in ((0, -hy), (1, hy)):
            for iz, szn in ((0, -hz), (1, hz)):
                p[(ix, iy, iz)] = (cx + sxn, cy + syn, cz + szn)

    def quad(a, b, c, d):
        return [[p[a], p[b], p[c]], [p[a], p[c], p[d]]]

    tris = []
    tris += quad((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))  # top  z+
    tris += quad((0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0))  # bot  z-
    tris += quad((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1))  # y-
    tris += quad((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0))  # y+
    tris += quad((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0))  # x-
    tris += quad((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1))  # x+
    return np.asarray(tris, dtype=np.float64)


def _box_walls_only(half: float, height: float) -> np.ndarray:
    """Only the 4 vertical side faces of a box (8 tris) — no top/bottom.

    Every triangle projects to a line in XY (area 0): the loader must
    skip them all and yield an all-zero heightmap.
    """
    h = half
    z0, z1 = 0.0, height
    walls = [
        # x = -h face
        [(-h, -h, z0), (-h, h, z0), (-h, h, z1)],
        [(-h, -h, z0), (-h, h, z1), (-h, -h, z1)],
        # x = +h face
        [(h, -h, z0), (h, h, z0), (h, h, z1)],
        [(h, -h, z0), (h, h, z1), (h, -h, z1)],
        # y = -h face
        [(-h, -h, z0), (h, -h, z0), (h, -h, z1)],
        [(-h, -h, z0), (h, -h, z1), (-h, -h, z1)],
        # y = +h face
        [(-h, h, z0), (h, h, z0), (h, h, z1)],
        [(-h, h, z0), (h, h, z1), (-h, h, z1)],
    ]
    return np.asarray(walls, dtype=np.float64)


def _pyramid(base_half: float, height: float) -> np.ndarray:
    """Square pyramid: base at z=0, apex at (0, 0, height). 6 tris."""
    b = base_half
    A = (-b, -b, 0.0)
    B = (b, -b, 0.0)
    C = (b, b, 0.0)
    D = (-b, b, 0.0)
    P = (0.0, 0.0, height)
    tris = [
        [A, B, C], [A, C, D],            # base (hidden bottom)
        [A, B, P], [B, C, P], [C, D, P], [D, A, P],  # 4 slanted faces
    ]
    return np.asarray(tris, dtype=np.float64)


def _uv_sphere(R: float, n_lat: int = 64, n_lon: int = 64) -> np.ndarray:
    """Closed UV sphere of radius R centered at the origin."""
    def s(th, ph):
        return (
            R * math.sin(th) * math.cos(ph),
            R * math.sin(th) * math.sin(ph),
            R * math.cos(th),
        )

    tris = []
    for i in range(n_lat):
        th0 = math.pi * i / n_lat
        th1 = math.pi * (i + 1) / n_lat
        for j in range(n_lon):
            ph0 = 2 * math.pi * j / n_lon
            ph1 = 2 * math.pi * (j + 1) / n_lon
            p00, p01 = s(th0, ph0), s(th0, ph1)
            p10, p11 = s(th1, ph0), s(th1, ph1)
            tris.append([p00, p10, p11])
            tris.append([p00, p11, p01])
    return np.asarray(tris, dtype=np.float64)


def _tilted_triangle() -> np.ndarray:
    """Single non-closed triangle with a varying-z (tilted) surface."""
    return np.asarray(
        [[(-4.0, -4.0, 0.0), (4.0, -4.0, 0.0), (0.0, 4.0, 3.0)]],
        dtype=np.float64,
    )


def _write_stl(tris: np.ndarray, path) -> str:
    """Write triangles to a binary STL at `path`; return the path str.

    `remove_empty_areas=False` so degenerate (vertical-wall) triangles
    survive into the file — the loader, not the writer, must skip them.
    """
    data = np.zeros(len(tris), dtype=stl_mesh.Mesh.dtype)
    m = stl_mesh.Mesh(data, remove_empty_areas=False)
    if len(tris):
        m.vectors[:] = tris
    out = str(path)
    m.save(out)
    return out


# ---------------------------------------------------------------------------
# 1. Cube — uniform top, zero outside, lifted base.
# ---------------------------------------------------------------------------
def test_cube_uniform_top_zero_outside(tmp_path):
    p = _write_stl(_box(0, 0, 0, 10, 10, 10), tmp_path / "cube.stl")
    hm = load_stl_heightmap(p, (200, 240), 0.1)

    H, W = hm.shape
    # Well inside the 10 mm footprint (|x|,|y| < 4 mm).
    inside = hm[H // 2 - 30:H // 2 + 30, W // 2 - 30:W // 2 + 30]
    np.testing.assert_allclose(inside, 10.0, atol=1e-9)
    # Corner pixels are bare stage.
    assert hm[0, 0] == 0.0
    assert hm[-1, -1] == 0.0


def test_cube_max_equals_z_extent(tmp_path):
    p = _write_stl(_box(0, 0, 0, 10, 10, 10), tmp_path / "cube.stl")
    hm = load_stl_heightmap(p, (200, 240), 0.1)
    np.testing.assert_allclose(hm.max(), 10.0, atol=1e-9)


def test_cube_min_is_zero(tmp_path):
    p = _write_stl(_box(0, 0, 0, 10, 10, 10), tmp_path / "cube.stl")
    hm = load_stl_heightmap(p, (200, 240), 0.1)
    assert hm.min() == 0.0


def test_cube_shape_and_dtype(tmp_path):
    p = _write_stl(_box(0, 0, 0, 10, 10, 10), tmp_path / "cube.stl")
    hm = load_stl_heightmap(p, (200, 240), 0.1)
    assert hm.shape == (200, 240)
    assert hm.dtype == np.float64
    assert np.all(np.isfinite(hm))


# ---------------------------------------------------------------------------
# 2. Pyramid — peak at apex height, monotonic falloff.
# ---------------------------------------------------------------------------
def test_pyramid_peak_and_falloff(tmp_path):
    h = 6.0
    p = _write_stl(_pyramid(5.0, h), tmp_path / "pyr.stl")
    hm = load_stl_heightmap(p, (220, 220), 0.1)
    H, W = hm.shape
    cr, cc = H // 2, W // 2

    # Apex: even grid puts the center ~0.07 mm off the apex axis, and
    # the pyramid face slope is h/base_half = 1.2 mm/mm, so the discrete
    # peak sits ~0.09 mm under h. Barycentric on the planar faces is
    # exact; the only error is that sub-pixel sampling offset.
    np.testing.assert_allclose(hm.max(), h, atol=0.1)

    center = hm[cr, cc]
    mid = hm[cr, cc + 25]      # ~2.5 mm out along +x
    edge = hm[cr, cc + 48]     # ~4.8 mm out, near base perimeter
    assert center > mid > edge, (center, mid, edge)
    assert edge >= 0.0
    assert hm.min() == 0.0


# ---------------------------------------------------------------------------
# 3. Tilted single triangle (open mesh, no closed solid).
# ---------------------------------------------------------------------------
def test_tilted_triangle_no_nan_inf_reflects_tilt(tmp_path):
    p = _write_stl(_tilted_triangle(), tmp_path / "tilt.stl")
    hm = load_stl_heightmap(p, (160, 160), 0.1)

    assert np.all(np.isfinite(hm))           # no NaN, no Inf anywhere
    assert hm.min() == 0.0                    # lifted to the z=0 base
    # Apex vertex is at z=3 -> some covered pixel near it is ~3.
    np.testing.assert_allclose(hm.max(), 3.0, atol=0.1)
    # Tilt direction: per _centered_grid_mm, larger row index -> larger
    # (more positive) Y. The apex is at +y (z=3), the base edge at -y
    # (z=0), so the +y row (H//2 + 30) must out-rank the -y row.
    H, W = hm.shape
    assert hm[H // 2 + 30, W // 2] > hm[H // 2 - 30, W // 2]


# ---------------------------------------------------------------------------
# 4. Closed sphere — upper envelope is a dome; peak == diameter.
# ---------------------------------------------------------------------------
def test_sphere_upper_envelope_peak_is_diameter(tmp_path):
    R = 4.0
    p = _write_stl(_uv_sphere(R, 72, 72), tmp_path / "sphere.stl")
    hm = load_stl_heightmap(p, (240, 240), 0.1)

    # Bottom hemisphere discarded by max-z; lift references its -R pole,
    # so peak == 2R (the diameter), within tessellation error.
    np.testing.assert_allclose(hm.max(), 2 * R, atol=0.12)
    assert hm.min() == 0.0
    assert np.all(hm >= -1e-12)               # bottom shell not leaking
    assert np.all(hm <= 2 * R + 1e-9)

    # Dome shape: center >> mid-radius > bare stage.
    H, W = hm.shape
    cr, cc = H // 2, W // 2
    assert hm[cr, cc] > hm[cr, cc + 20] > 0.0


# ---------------------------------------------------------------------------
# 5. Vertical-walls-only mesh — all triangles XY-degenerate.
# ---------------------------------------------------------------------------
def test_vertical_walls_only_is_all_zeros(tmp_path):
    p = _write_stl(_box_walls_only(5.0, 8.0), tmp_path / "walls.stl")
    hm = load_stl_heightmap(p, (180, 180), 0.1)
    np.testing.assert_array_equal(hm, np.zeros((180, 180), dtype=np.float64))
    assert hm.dtype == np.float64


# ---------------------------------------------------------------------------
# 6. Empty mesh — ValueError (documented contract).
# ---------------------------------------------------------------------------
def test_empty_mesh_raises_valueerror(tmp_path):
    p = _write_stl(np.zeros((0, 3, 3), dtype=np.float64), tmp_path / "e.stl")
    with pytest.raises(ValueError, match="no triangles"):
        load_stl_heightmap(p, (100, 100), 0.1)


def test_empty_mesh_bbox_raises_valueerror(tmp_path):
    p = _write_stl(np.zeros((0, 3, 3), dtype=np.float64), tmp_path / "e.stl")
    with pytest.raises(ValueError, match="no triangles"):
        get_stl_bbox_mm(p)


# ---------------------------------------------------------------------------
# 7. World-origin offset — XY centering makes it position-invariant.
# ---------------------------------------------------------------------------
def test_offset_part_centered_identically(tmp_path):
    at_origin = _write_stl(_box(0, 0, 0, 10, 10, 10), tmp_path / "o.stl")
    far = _write_stl(_box(100, 50, 0, 10, 10, 10), tmp_path / "f.stl")
    hm0 = load_stl_heightmap(at_origin, (200, 240), 0.1)
    hm1 = load_stl_heightmap(far, (200, 240), 0.1)
    # Pure translation removed by bbox-center centering -> identical
    # float ops -> bit-identical heightmaps.
    np.testing.assert_array_equal(hm0, hm1)


# ---------------------------------------------------------------------------
# 8 & 9. get_stl_bbox_mm extents.
# ---------------------------------------------------------------------------
def test_bbox_cube(tmp_path):
    p = _write_stl(_box(0, 0, 0, 10, 10, 10), tmp_path / "cube.stl")
    dx, dy, dz = get_stl_bbox_mm(p)
    np.testing.assert_allclose([dx, dy, dz], [10.0, 10.0, 10.0], atol=1e-6)


def test_bbox_asymmetric_box(tmp_path):
    # Asymmetric extents and an off-origin center: extents are still
    # max-min per axis, independent of placement.
    p = _write_stl(_box(7, -3, 12, 3.0, 7.0, 11.0), tmp_path / "abox.stl")
    dx, dy, dz = get_stl_bbox_mm(p)
    np.testing.assert_allclose([dx, dy, dz], [3.0, 7.0, 11.0], atol=1e-6)


# ---------------------------------------------------------------------------
# 10–12 are exercised above (shape/dtype, min==0, max==z-extent) across
# the cube/pyramid/sphere cases; this consolidates the contract on a
# non-cube part for independence.
# ---------------------------------------------------------------------------
def test_pyramid_shape_dtype_min_contract(tmp_path):
    p = _write_stl(_pyramid(5.0, 6.0), tmp_path / "pyr.stl")
    hm = load_stl_heightmap(p, (220, 200), 0.1)
    assert hm.shape == (220, 200)
    assert hm.dtype == np.float64
    assert np.all(np.isfinite(hm))
    assert hm.min() == 0.0
