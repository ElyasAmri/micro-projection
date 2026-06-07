"""GL-level test for HardwareScene.update_pose (Stage 6 projector-swap 3a).

`test_hardware_scene.py` is deliberately Qt-free (it targets the pure
`compute_arm_transforms`). The one 3a check that genuinely needs a real
`GLViewWidget` — confirming `update_pose`, through the new profile-plumbing,
still feeds the projection-cone item the Pico throw-ratio wireframe at the slider
distance — lives here, mirroring the `QApplication` fixture the other GUI tests
use. This pins the cone-builder branch wiring (Pico's empty `lens_options` must
take the `else` / throw-ratio path), which the pure tests can't exercise.

Path setup mirrors test_main_window_stl.py: `main_window`/`hardware_scene` use
`from src.gui...` imports, which need the repo root on sys.path.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pyqtgraph.opengl as gl  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from gui.hardware_scene import (  # noqa: E402
    KEY_PROJECTION_CONE,
    KEY_PROJECTOR_BODY,
    KEY_PROJECTOR_LENS,
    HardwareScene,
)
from scene import (  # noqa: E402
    PICO_GENIE,
    WINTECH_PRO4500,
    make_projection_cone_from_fov,
    make_projection_cone_wireframe,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _expected_pico_cone_segments(throw_mm: float) -> np.ndarray:
    """The (2M,3) line-segment pos a Pico throw-ratio cone expands to."""
    verts, edges = make_projection_cone_wireframe(throw_mm)
    return verts[edges.reshape(-1)].astype(np.float32)


def test_update_pose_draws_pico_throw_ratio_cone(qapp):
    """update_pose feeds the projection-cone item the Pico throw-ratio wireframe
    at the slider distance — proving the profile branch takes the `else`
    (wireframe) path for Pico, both by default and with profile=PICO_GENIE.

    Pose is the clip-triggering steep-projector case (theta_proj=-41, throw=149).
    """
    view = gl.GLViewWidget()
    hs = HardwareScene(view)
    throw = 149.0
    expected = _expected_pico_cone_segments(throw)

    # Default profile (PICO_GENIE).
    hs.update_pose(
        theta_camera_deg=30.0, theta_projector_deg=-41.0,
        projector_distance_mm=throw, camera_distance_mm=157.0,
    )
    drawn = np.asarray(hs._cones[KEY_PROJECTION_CONE].pos, dtype=np.float32)
    np.testing.assert_array_equal(drawn, expected)

    # Explicit profile=PICO_GENIE → identical drawn cone.
    hs.update_pose(
        theta_camera_deg=30.0, theta_projector_deg=-41.0,
        projector_distance_mm=throw, camera_distance_mm=157.0,
        profile=PICO_GENIE,
    )
    drawn2 = np.asarray(hs._cones[KEY_PROJECTION_CONE].pos, dtype=np.float32)
    np.testing.assert_array_equal(drawn2, expected)


def _body_extents(hs) -> np.ndarray:
    """(dx, dy, dz) extent of the projector body item's current mesh."""
    v = np.asarray(hs._items[KEY_PROJECTOR_BODY].opts["meshdata"].vertexes(), dtype=float)
    return v.max(axis=0) - v.min(axis=0)


def test_set_projector_profile_rebuilds_mesh(qapp):
    """set_projector_profile swaps the projector body/lens mesh in place:
    PRO4500 -> 84 x 54 x 145 box + 30 x 65 barrel lens; back to PICO_GENIE ->
    55^3 cube + 20 x 5 lens."""
    view = gl.GLViewWidget()
    hs = HardwareScene(view)
    # Built Pico by default.
    np.testing.assert_allclose(_body_extents(hs), [55.0, 55.0, 55.0], atol=1e-4)

    hs.set_projector_profile(WINTECH_PRO4500)
    np.testing.assert_allclose(_body_extents(hs), [84.0, 54.0, 145.0], atol=1e-4)
    lens_v = np.asarray(
        hs._items[KEY_PROJECTOR_LENS].opts["meshdata"].vertexes(), dtype=float
    )
    np.testing.assert_allclose(
        lens_v.max(axis=0) - lens_v.min(axis=0), [30.0, 30.0, 65.0], atol=1e-4
    )

    hs.set_projector_profile(PICO_GENIE)
    np.testing.assert_allclose(_body_extents(hs), [55.0, 55.0, 55.0], atol=1e-4)


def _drawn_cone(hs) -> np.ndarray:
    return np.asarray(hs._cones[KEY_PROJECTION_CONE].pos, dtype=np.float32)


def test_update_pose_active_lens_selects_fov_cone(qapp):
    """active_lens_index picks which PRO4500 lens drives the drawn FOV cone:
    index 0 -> 92 mm (65.6x41 @ 92); index 1 / None -> 184 mm (131.2x82 @ 184)."""
    view = gl.GLViewWidget()
    hs = HardwareScene(view)
    common = dict(theta_camera_deg=0.0, theta_projector_deg=0.0,
                  camera_distance_mm=157.0, profile=WINTECH_PRO4500)

    # 92 mm lens (index 0): base 65.6 x 41 at z=92.
    hs.update_pose(projector_distance_mm=92.0, active_lens_index=0, **common)
    v, e = make_projection_cone_from_fov(65.6, 41.0, 92.0)
    cone92 = v[e.reshape(-1)].astype(np.float32)
    np.testing.assert_array_equal(_drawn_cone(hs), cone92)

    # 184 mm lens (index 1): base 131.2 x 82 at z=184; differs from the 92 cone.
    hs.update_pose(projector_distance_mm=184.0, active_lens_index=1, **common)
    v2, e2 = make_projection_cone_from_fov(131.2, 82.0, 184.0)
    cone184 = v2[e2.reshape(-1)].astype(np.float32)
    np.testing.assert_array_equal(_drawn_cone(hs), cone184)
    assert not np.array_equal(cone92, cone184)

    # None -> default_lens_index (1 == 184): identical to explicit index 1.
    hs.update_pose(projector_distance_mm=184.0, active_lens_index=None, **common)
    np.testing.assert_array_equal(_drawn_cone(hs), cone184)


def test_update_pose_coverage_differs_by_lens(qapp):
    """A +/-50 mm-wide, +/-20 mm-tall surface sits inside the 184 mm FOV cone but
    outside the closer/narrower 92 mm FOV cone -> coverage fires for 92 only.

    The two lenses share a cone half-angle (slopes equal); the discrimination is
    the working distance (apex height): half-width at the surface = fov/2 = 32.8
    (92) vs 65.6 (184) mm. shape (H,W): H -> y(+/-20), W -> x(+/-50) @ 0.1 mm/px.
    """
    view = gl.GLViewWidget()
    hs = HardwareScene(view)
    hm = np.zeros((400, 1000), dtype=np.float64)
    common = dict(theta_camera_deg=0.0, theta_projector_deg=0.0,
                  camera_distance_mm=157.0, heightmap_mm=hm,
                  surface_pixel_size_mm=0.1, profile=WINTECH_PRO4500)
    s92 = hs.update_pose(projector_distance_mm=92.0, active_lens_index=0, **common)
    s184 = hs.update_pose(projector_distance_mm=184.0, active_lens_index=1, **common)
    assert s92.surface_outside_projector_cone        # narrow 92 cone misses the edges
    assert not s184.surface_outside_projector_cone    # wide 184 cone covers them
