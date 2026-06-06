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
    PRO4500 -> 84 x 54 x 210 box; back to PICO_GENIE -> 55^3 cube."""
    view = gl.GLViewWidget()
    hs = HardwareScene(view)
    # Built Pico by default.
    np.testing.assert_allclose(_body_extents(hs), [55.0, 55.0, 55.0], atol=1e-4)

    hs.set_projector_profile(WINTECH_PRO4500)
    np.testing.assert_allclose(_body_extents(hs), [84.0, 54.0, 210.0], atol=1e-4)
    lens_v = np.asarray(
        hs._items[KEY_PROJECTOR_LENS].opts["meshdata"].vertexes(), dtype=float
    )
    np.testing.assert_allclose(
        lens_v.max(axis=0) - lens_v.min(axis=0), [20.0, 20.0, 5.0], atol=1e-4
    )

    hs.set_projector_profile(PICO_GENIE)
    np.testing.assert_allclose(_body_extents(hs), [55.0, 55.0, 55.0], atol=1e-4)
