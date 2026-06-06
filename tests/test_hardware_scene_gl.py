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

from gui.hardware_scene import KEY_PROJECTION_CONE, HardwareScene  # noqa: E402
from scene import PICO_GENIE, make_projection_cone_wireframe  # noqa: E402


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
