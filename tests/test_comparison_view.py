"""Tests for the RecoveredComparisonView (Stage 5 sub-task 4).

All tests need a QApplication (GL items), so they use the `qapp` fixture.
The translucent-path assertions lock the exact construction the 4d.1 probe
blessed (setGLOptions("translucent") + alpha<1 + depthValue 1); the rendered
result is eyeballed via the comparison smoke screenshots.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from gui.comparison_view import (  # noqa: E402
    _GROUND_TRUTH_COLOR,
    _RECOVERED_COLOR,
    RecoveredComparisonView,
)

SHAPE = (550, 680)


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_both_surfaces_visible_by_default(qapp):
    v = RecoveredComparisonView()
    assert v._recovered_item.visible() is True
    assert v._ground_truth_item.visible() is True


def test_set_recovered_visible_toggles(qapp):
    v = RecoveredComparisonView()
    v.set_recovered_visible(False)
    assert v._recovered_item.visible() is False
    v.set_recovered_visible(True)
    assert v._recovered_item.visible() is True
    # Ground truth untouched.
    assert v._ground_truth_item.visible() is True


def test_set_ground_truth_visible_toggles(qapp):
    v = RecoveredComparisonView()
    v.set_ground_truth_visible(False)
    assert v._ground_truth_item.visible() is False
    v.set_ground_truth_visible(True)
    assert v._ground_truth_item.visible() is True
    assert v._recovered_item.visible() is True


def test_ground_truth_uses_blessed_translucent_path(qapp):
    """Lock the 4d.1-validated construction: glOptions translucent + a
    higher depthValue so it draws after the opaque recovered surface."""
    from pyqtgraph.opengl.GLGraphicsItem import GLOptions

    v = RecoveredComparisonView()
    gt = v._ground_truth_item
    assert gt._GLGraphicsItem__glOpts == GLOptions["translucent"]
    assert gt.depthValue() == 1


def test_recovered_is_opaque(qapp):
    from pyqtgraph.opengl.GLGraphicsItem import GLOptions

    v = RecoveredComparisonView()
    rec = v._recovered_item
    assert rec._GLGraphicsItem__glOpts == GLOptions["opaque"]
    assert rec.depthValue() == 0


def test_set_data_renders_both_surfaces(qapp):
    v = RecoveredComparisonView()
    rec = np.zeros(SHAPE, dtype=np.float64)
    rec[100, 100] = 3.0
    gt = np.zeros(SHAPE, dtype=np.float64)
    gt[200, 200] = 7.0

    v.set_data(rec, gt)

    # Both items carry z data of the transposed (W, H) shape.
    assert v._recovered_item._z.shape == (SHAPE[1], SHAPE[0])
    assert v._ground_truth_item._z.shape == (SHAPE[1], SHAPE[0])


def test_set_data_colors_match_identity_and_translucency(qapp):
    v = RecoveredComparisonView()
    v.set_data(np.zeros(SHAPE), np.ones(SHAPE))

    rec_colors = v._recovered_item._meshdata._vertexColors
    gt_colors = v._ground_truth_item._meshdata._vertexColors
    # Recovered fully opaque; ground truth translucent (alpha 0.5).
    assert rec_colors[:, 3].min() == pytest.approx(1.0)
    assert gt_colors[:, 3].max() == pytest.approx(_GROUND_TRUTH_COLOR[3])
    assert _GROUND_TRUTH_COLOR[3] < 1.0
    assert _RECOVERED_COLOR[3] == 1.0


def test_set_data_fits_grid_z_extent_to_combined_range(qapp):
    v = RecoveredComparisonView()
    rec = np.zeros(SHAPE, dtype=np.float64)
    rec[100, 100] = 3.0
    gt = np.zeros(SHAPE, dtype=np.float64)
    gt[200, 200] = 7.0  # combined max comes from ground truth

    v.set_data(rec, gt)

    # Grid Z labels reflect the combined max (7), proving set_z_extent ran
    # with the combined range, not just one surface.
    z_label_texts = [it.text for it in v._grid._z_label_items]
    assert "7" in z_label_texts
    assert "0" in z_label_texts


def test_grid_is_embedded_in_view(qapp):
    v = RecoveredComparisonView()
    # Every CoordinateGrid item is a child of the view.
    for item in v._grid.items():
        assert item in v.items


def _capture_z_extent(monkeypatch, view):
    """Capture the exact (z_min, z_max) set_data hands to the grid."""
    captured = {}
    monkeypatch.setattr(
        view._grid,
        "set_z_extent",
        lambda lo, hi: captured.update(lo=lo, hi=hi),
    )
    return captured


def test_steep_dome_z_extent_uses_p99_not_raw_max(qapp, monkeypatch):
    """Stage 6 B.3 polish: with z_max_percentile, the view's z_max is the p99
    of the combined displayed arrays (so the spike sits outside the box), while
    z_min stays the raw combined min. The DATA is unchanged — view bounds only.
    """
    v = RecoveredComparisonView()
    captured = _capture_z_extent(monkeypatch, v)

    # Gentle bulk (0..100) plus one crushing central peak, the steep-dome shape.
    rec = np.linspace(0.0, 100.0, int(np.prod(SHAPE))).reshape(SHAPE)
    rec[0, 0] = 6000.0
    gt = rec.copy()
    combined = np.concatenate((rec.ravel(), gt.ravel()))

    v.set_data(rec, gt, z_max_percentile=99.0)

    assert captured["hi"] == pytest.approx(float(np.percentile(combined, 99.0)))
    assert captured["hi"] < float(combined.max())          # peak excluded
    assert captured["lo"] == pytest.approx(float(combined.min()))  # raw min


def test_non_steep_z_extent_uses_raw_min_max(qapp, monkeypatch):
    """Default (z_max_percentile=None) keeps the historical raw combined
    min/max extent byte-identical — non-steep surfaces are unaffected."""
    v = RecoveredComparisonView()
    captured = _capture_z_extent(monkeypatch, v)

    rec = np.zeros(SHAPE, dtype=np.float64)
    rec[100, 100] = 3.0
    gt = np.zeros(SHAPE, dtype=np.float64)
    gt[200, 200] = 7.0  # combined max comes from ground truth

    v.set_data(rec, gt)  # default: no percentile

    assert captured["hi"] == pytest.approx(7.0)  # raw combined max
    assert captured["lo"] == pytest.approx(0.0)  # raw combined min
