"""Occlusion analysis + stress surfaces: slope map correctness, directional
horizon-scan shadows, and the stress family's designed failure modes."""
import sys
from pathlib import Path

import numpy as np

# The occlusion/surfaces modules live in the sim engine, not the app package
# (same path the backend inserts lazily in backend.base).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "simulation"))

import occlusion  # noqa: E402
import surfaces  # noqa: E402


def test_flat_has_no_slope_or_shadow():
    m = occlusion.analyze(surfaces.SURFACES["flat"])
    assert m["max_slope_deg"] == 0.0
    assert m["camera_hidden_pct"] == 0.0 and m["projector_shadow_pct"] == 0.0


def test_slope_of_inclined_plane():
    z = np.fromfunction(lambda r, c: c * 0.1, (50, 80))  # dz/dx = 1 at pitch 0.1
    ang = occlusion.slope_deg(z, pitch_x_mm=0.1, pitch_y_mm=0.1)
    np.testing.assert_allclose(ang[1:-1, 1:-1], 45.0, atol=1e-6)


def test_step_shadow_length_and_direction():
    # A 2mm-high plateau on the +x half; rays from +x at 45 degrees shadow a
    # strip of length h/tan(45) = 2mm on the low side next to the wall.
    pitch, w, h_mm = 0.1, 400, 2.0
    z = np.zeros((60, w))
    z[:, w // 2:] = h_mm
    frac = occlusion.shadow_fraction(z, pitch, elevation_deg=45.0, azimuth="+x")
    expected = (h_mm / 1.0) / (w * pitch)  # 2mm of 40mm field
    assert abs(frac - expected) < 0.005
    # From -x the wall faces away -- nothing is hidden.
    assert occlusion.shadow_fraction(z, pitch, 45.0, azimuth="-x") == 0.0


def test_validation_surfaces_stay_shadow_free():
    for name in ("bump", "offset_bump", "crater", "ridge", "twin_bump", "rough"):
        m = occlusion.analyze(surfaces.SURFACES[name])
        assert m["camera_hidden_pct"] == 0.0, name
        assert m["max_slope_deg"] < 11.0, name


def test_stress_surfaces_exceed_the_budget():
    ring = occlusion.analyze(surfaces.SURFACES["ring_crater"])
    assert 60.0 < ring["max_slope_deg"] < 72.0  # designed ~65 deg walls
    assert ring["camera_hidden_pct"] > 1.0      # the inner wall self-occludes
    cross = occlusion.analyze(surfaces.SURFACES["cross_groove"])
    assert cross["camera_hidden_pct"] > 0.3     # the x-groove hides its wall


def test_terrace_has_real_steps():
    x, y = occlusion.field_grid(500, 380)
    z = surfaces.SURFACES["terrace"](x, y)
    assert float(np.abs(np.diff(z, axis=1)).max()) >= 0.5 - 1e-9
    # Steps quantize to multiples of the step height.
    assert np.allclose(z / 0.5, np.round(z / 0.5), atol=1e-9)


def test_shadow_mask_orientation_roundtrip():
    # The same physical step must produce the same physical mask whichever
    # way the grid is oriented; only the scan bookkeeping changes.
    z = np.zeros((40, 200))
    z[:, 100:] = 2.0  # high plateau on the high-column side
    m_px = occlusion.shadow_mask(z, 0.1, 45.0, azimuth="+x")
    m_mx = occlusion.shadow_mask(z[:, ::-1], 0.1, 45.0, azimuth="-x")
    assert np.array_equal(m_px, m_mx[:, ::-1])
    m_py = occlusion.shadow_mask(z.T, 0.1, 45.0, azimuth="+y")
    assert np.array_equal(m_px, m_py.T)
    # Rays from +x with the plateau toward +x: the strip just left of the
    # wall is hidden (h/tan(45) = 20px, exact-distance boundary exclusive);
    # nothing on the plateau is.
    assert m_px[:, 81:100].all() and not m_px[:, 100:].any()
    assert not m_px[:, :80].any()


def test_camera_hidden_mask_handles_descending_x():
    # pixel_to_world's grid runs x DESCENDING with column; the helper must
    # put the hidden strip on the same *physical* side either way.
    n = 200
    x_asc = np.tile(np.linspace(-10, 10, n), (40, 1))
    z_asc = np.where(x_asc > 0, 2.0, 0.0)  # wall at x=0, high side +x
    m_asc = occlusion.camera_hidden_mask(z_asc, x_asc, 20.0 / (n - 1))
    x_desc = x_asc[:, ::-1]
    m_desc = occlusion.camera_hidden_mask(z_asc[:, ::-1], x_desc, 20.0 / (n - 1))
    # Same physical mask: hidden strip sits at x slightly < 0 in both.
    assert np.array_equal(m_asc, m_desc[:, ::-1])
    assert m_asc[0, np.searchsorted(x_asc[0], -0.5)]
    assert not m_asc[0, np.searchsorted(x_asc[0], 5.0)]
