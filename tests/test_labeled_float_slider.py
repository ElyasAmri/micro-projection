"""Tests for LabeledFloatSlider's numeric-entry spinbox (Stage 5 sub-task 4d.9).

The widget needs a QApplication, so all tests use the `qapp` fixture.
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from gui.main_window import LabeledFloatSlider  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _whole_degree_slider():
    # Mirrors theta_projector: -75..75, default 30, step 1.0 (decimals 0).
    return LabeledFloatSlider("theta", -75.0, 75.0, 30.0, 1.0, suffix="°")


def test_initial_spinbox_matches_default(qapp):
    s = _whole_degree_slider()
    assert s.value() == 30.0
    assert s._spinbox.value() == 30.0


def test_spinbox_reflects_slider_move(qapp):
    s = _whole_degree_slider()
    s._slider.setValue(int(round(10.0 * s._scale)))  # drag slider to 10
    assert s.value() == 10.0
    assert s._spinbox.value() == 10.0


def test_typing_value_moves_slider_and_fires_once(qapp):
    s = _whole_degree_slider()
    emissions = []
    s.valueChanged.connect(emissions.append)

    s._spinbox.setValue(20.0)  # simulate a committed entry

    assert s.value() == 20.0
    assert s._slider.value() == int(round(20.0 * s._scale))
    assert emissions == [20.0]  # exactly one emission, no feedback loop


def test_offgrid_entry_snaps_to_step(qapp):
    s = _whole_degree_slider()  # whole-degree grid
    s._spinbox.setValue(15.7)
    # Snaps to the nearest whole degree, in both the value and the spinbox.
    assert s.value() == 16.0
    assert s._spinbox.value() == 16.0


def test_out_of_range_entry_clamps(qapp):
    s = _whole_degree_slider()  # range [-75, 75]
    s._spinbox.setValue(200.0)
    assert s.value() == 75.0
    assert s._spinbox.value() == 75.0
    s._spinbox.setValue(-200.0)
    assert s.value() == -75.0


def test_fine_step_slider_preserves_precision(qapp):
    # Mirrors gaussian_amplitude: 0..120, default 0.5, step 0.01 (decimals 2).
    s = LabeledFloatSlider("amp", 0.0, 120.0, 0.5, 0.01)
    s._spinbox.setValue(3.27)
    assert s.value() == pytest.approx(3.27)
    assert s._spinbox.value() == pytest.approx(3.27)


def test_set_value_contract_syncs_spinbox(qapp):
    s = _whole_degree_slider()
    emissions = []
    s.valueChanged.connect(emissions.append)

    s.set_value(-20.0)

    assert s.value() == -20.0
    assert s._spinbox.value() == -20.0
    assert emissions == [-20.0]  # set_value still emits once
