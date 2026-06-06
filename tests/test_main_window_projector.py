"""GUI-level tests for the projector selector (Stage 6 projector-swap 3b).

Constructs a real MainWindow and drives the projector QComboBox to confirm the
end-to-end wiring: flipping the active profile rebuilds the body mesh, updates
the info-panel strings, and applies "lens fixes the WD" (the throw slider is set
to the active lens's working distance and locked for a lens-table projector,
restored + re-enabled for the free-throw Pico).

Path setup mirrors test_main_window_stl.py.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from gui.main_window import MainWindow  # noqa: E402
from gui.hardware_scene import arm_lens_front_world  # noqa: E402
from scene import PICO_GENIE, WINTECH_PRO4500  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def window(qapp):
    w = MainWindow()
    yield w
    w.close()


# PROJECTOR_PROFILES order: 0 = Pico, 1 = PRO4500.
_PICO_IDX, _PRO_IDX = 0, 1


def test_default_projector_is_pico(window):
    assert window._projector_profile is PICO_GENIE
    assert window.projector_combo.currentIndex() == _PICO_IDX
    assert window.projector_distance.isEnabled()
    assert window._info_projector_label.text() == "Pico Genie Impact 2.0 Plus Elite"
    assert window._info_throw_ratio_label.text() == "1.2:1"
    # Pico has no lens choice -> the lens combo is hidden.
    assert window.lens_combo.isHidden()


def test_lens_selector_round_trip_preserves_pico_throw(window):
    """Pico (throw T) -> PRO4500 (slider locks 184) -> pick 92 mm (slider 92) ->
    back to Pico (slider MUST restore T, not 92 or 184).

    This is the exact path that exercises the _saved_projector_throw_mm ownership
    boundary: _on_lens_changed must NOT overwrite the saved Pico throw, so the
    final Pico restore returns the ORIGINAL value.
    """
    T = window.projector_distance.value()              # Pico free-throw default (150)

    # Pico -> PRO4500: lens combo populates + shows, defaults to 184; slider locks.
    window.projector_combo.setCurrentIndex(_PRO_IDX)
    assert window._projector_profile is WINTECH_PRO4500
    assert not window.lens_combo.isHidden()
    assert window.lens_combo.count() == 2
    assert window.lens_combo.currentIndex() == WINTECH_PRO4500.default_lens_index == 1
    assert window._active_lens_index == 1
    assert window.projector_distance.value() == 184.0
    assert not window.projector_distance.isEnabled()

    # Pick the 92 mm lens (index 0): slider re-locks to 92; profile stays canonical.
    window.lens_combo.setCurrentIndex(0)
    assert window._active_lens_index == 0
    assert window.projector_distance.value() == 92.0
    assert not window.projector_distance.isEnabled()
    assert window._projector_profile is WINTECH_PRO4500   # canonical object unchanged

    # Back to Pico: slider restores the ORIGINAL T (not 92 or 184); combo hidden.
    window.projector_combo.setCurrentIndex(_PICO_IDX)
    assert window._projector_profile is PICO_GENIE
    assert window.projector_distance.isEnabled()
    assert window.projector_distance.value() == T
    assert window.lens_combo.isHidden()


def test_select_pro4500_flips_profile_locks_wd_and_updates_info(window):
    saved = window.projector_distance.value()        # Pico free-throw default (150)

    window.projector_combo.setCurrentIndex(_PRO_IDX)  # fires _on_projector_changed

    # Profile flipped.
    assert window._projector_profile is WINTECH_PRO4500
    # Lens fixes the WD: slider set to the active lens WD (184) and LOCKED.
    lens = WINTECH_PRO4500.lens_options[WINTECH_PRO4500.default_lens_index]
    assert window.projector_distance.value() == lens.working_distance_mm == 184.0
    assert not window.projector_distance.isEnabled()
    # Info panel: name updated, throw-ratio blanked (FOV/lens-based, no ratio).
    assert window._info_projector_label.text() == "Wintech PRO4500"
    assert window._info_throw_ratio_label.text() == "—"

    # The single source (slider value == WD) drives the readout too: the
    # projector lens-front sits on-axis at z = WD + recess (186) for PRO4500.
    coords = arm_lens_front_world(
        theta_cam_deg=window.theta_camera.value(),
        theta_proj_deg=0.0,
        proj_dist_mm=window.projector_distance.value(),
        cam_dist_mm=window.camera_distance.value(),
        profile=window._projector_profile,
    )
    # theta_projector may be non-zero by default; check on a vertical probe.
    vert = arm_lens_front_world(0.0, 0.0, window.projector_distance.value(),
                                window.camera_distance.value(),
                                profile=WINTECH_PRO4500)["projector"]
    np.testing.assert_allclose(vert, [0.0, 0.0, 186.0], atol=1e-4)


def test_switch_back_to_pico_restores_and_unlocks(window):
    saved = window.projector_distance.value()         # Pico default (150)
    window.projector_combo.setCurrentIndex(_PRO_IDX)   # lock to 184
    window.projector_combo.setCurrentIndex(_PICO_IDX)  # restore

    assert window._projector_profile is PICO_GENIE
    assert window.projector_distance.isEnabled()
    assert window.projector_distance.value() == saved   # restored free-throw value
    assert window._info_projector_label.text() == "Pico Genie Impact 2.0 Plus Elite"
    assert window._info_throw_ratio_label.text() == "1.2:1"
