"""OrbitCanvas rotation-gizmo behavior: when it engages, the camera basis it
projects the gizmo with, and the azimuth delta it reports (the paint path
itself is exercised by rendering the widget offscreen)."""
from __future__ import annotations

import math

import pytest

from ui.canvas import OrbitCanvas

VIEW = {"azimuth": 10.0, "elevation": 20.0, "distance": 0.6}


def test_hint_hidden_when_settled(qapp):
    canvas = OrbitCanvas("rigCanvas")
    canvas.set_view_hint(VIEW, dict(VIEW), rendering=False)
    assert not canvas._hint_active()


def test_hint_shown_while_rendering(qapp):
    canvas = OrbitCanvas("rigCanvas")
    canvas.set_view_hint(VIEW, dict(VIEW), rendering=True)
    assert canvas._hint_active()


def test_hint_shown_when_target_diverges(qapp):
    canvas = OrbitCanvas("rigCanvas")
    for key, target in (("azimuth", 40.0), ("elevation", 50.0), ("distance", 0.8)):
        canvas.set_view_hint({**VIEW, key: target}, dict(VIEW), rendering=False)
        assert canvas._hint_active(), key


def test_hint_needs_both_views(qapp):
    canvas = OrbitCanvas("rigCanvas")
    canvas.set_view_hint(VIEW, None, rendering=True)
    assert not canvas._hint_active()


def test_active_hint_paints_offscreen(qapp):
    """The HUD draw path runs without error on a real (offscreen) paint."""
    canvas = OrbitCanvas("rigCanvas")
    canvas.resize(400, 300)
    canvas.set_view_hint({**VIEW, "azimuth": 75.0}, dict(VIEW), rendering=True)
    assert not canvas.grab().isNull()


def test_azimuth_delta_wraps_the_shortest_way():
    assert OrbitCanvas._az_delta(350.0, 10.0) == -20.0
    assert OrbitCanvas._az_delta(10.0, 350.0) == 20.0
    assert OrbitCanvas._az_delta(180.0, 0.0) == -180.0


def test_camera_basis_is_orthonormal():
    right, up = OrbitCanvas._camera_basis(37.0, 55.0)
    assert math.dist(right, (0, 0, 0)) == pytest.approx(1.0)
    assert math.dist(up, (0, 0, 0)) == pytest.approx(1.0)
    assert sum(a * b for a, b in zip(right, up)) == pytest.approx(0.0)


def test_world_up_projection_tracks_elevation():
    """Looking from low elevation, the world Z axis fills the view vertically;
    looking straight down it foreshortens toward a point."""
    z = (0.0, 0.0, 1.0)

    def screen_len(el):
        right, up = OrbitCanvas._camera_basis(0.0, el)
        return math.hypot(sum(a * b for a, b in zip(z, right)),
                          sum(a * b for a, b in zip(z, up)))

    assert screen_len(5.0) == pytest.approx(math.cos(math.radians(5.0)))
    assert screen_len(85.0) < 0.1 < screen_len(5.0)


def test_azimuth_spins_the_projected_x_axis():
    x = (1.0, 0.0, 0.0)
    angles = []
    for az in (0.0, 90.0):
        right, up = OrbitCanvas._camera_basis(az, 30.0)
        angles.append((sum(a * b for a, b in zip(x, right)),
                       sum(a * b for a, b in zip(x, up))))
    (sx0, _), (sx90, _) = angles
    assert sx0 == pytest.approx(0.0)     # x points at the viewer at az=0
    assert sx90 == pytest.approx(-1.0)   # a quarter turn puts it on the left
