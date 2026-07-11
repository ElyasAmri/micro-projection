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
