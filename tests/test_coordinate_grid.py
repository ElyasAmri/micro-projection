"""Tests for the labeled XYZ coordinate-grid component (Stage 5 sub-task 3).

Two layers, matching the component's design:
- Pure `compute_axis_ticks` tests: headless, no Qt/GL.
- `CoordinateGrid` GL-assembly tests: need a QApplication (GLTextItem builds
  a QFont), so they use the `qapp` fixture.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from gui.coordinate_grid import (  # noqa: E402
    CoordinateGrid,
    _nice_step,
    compute_axis_ticks,
    compute_z_ticks,
)

# Standard math-grid extent (recon Q3): (550, 680) at 0.1 mm/px, centered.
SHAPE = (550, 680)
PS = 0.1
X_MAX = (680 - 1) / 2.0 * PS  # 33.95
Y_MAX = (550 - 1) / 2.0 * PS  # 27.45


# ---------------------------------------------------------------------------
# Pure tick-logic tests.
# ---------------------------------------------------------------------------
def _positions(ticks):
    return [p for p, _ in ticks]


def _labels(ticks):
    return [s for _, s in ticks]


def test_x_extent_ticks_step_10():
    ticks = compute_axis_ticks(-X_MAX, X_MAX)
    assert _positions(ticks) == [-30, -20, -10, 0, 10, 20, 30]
    assert _labels(ticks) == ["-30", "-20", "-10", "0", "10", "20", "30"]


def test_y_extent_ticks_step_10():
    ticks = compute_axis_ticks(-Y_MAX, Y_MAX)
    assert _positions(ticks) == [-20, -10, 0, 10, 20]


def test_submm_z_range_decimal_labels():
    ticks = compute_axis_ticks(0.0, 0.5)
    assert _positions(ticks) == pytest.approx([0.0, 0.1, 0.2, 0.3, 0.4, 0.5])
    assert _labels(ticks) == ["0.0", "0.1", "0.2", "0.3", "0.4", "0.5"]


def test_large_z_range_step_10():
    ticks = compute_axis_ticks(0.0, 50.0)
    assert _positions(ticks) == [0, 10, 20, 30, 40, 50]


@pytest.mark.parametrize(
    "span, expected_step",
    [
        (7.0, 1.0),    # 7/7 = 1.0  -> 1
        (14.0, 2.0),   # 14/7 = 2.0 -> 2
        (28.0, 5.0),   # 28/7 = 4.0 -> 5
        (70.0, 10.0),  # 70/7 = 10  -> 10
        (3.5, 0.5),    # 3.5/7 = 0.5 -> 0.5
    ],
)
def test_nice_step_selection(span, expected_step):
    # Step is derived from span / target_ticks (default 7).
    assert _nice_step(span / 7) == pytest.approx(expected_step)


def test_ticks_sorted_within_bounds_and_include_zero():
    ticks = compute_axis_ticks(-X_MAX, X_MAX)
    pos = _positions(ticks)
    assert pos == sorted(pos)
    assert all(-X_MAX - 1e-9 <= p <= X_MAX + 1e-9 for p in pos)
    assert 0.0 in pos


def test_degenerate_equal_min_max_single_tick():
    # Flat mode / startup-before-surface: no crash, one tick.
    assert compute_axis_ticks(0.0, 0.0) == [(0.0, "0")]
    ticks = compute_axis_ticks(5.0, 5.0)
    assert len(ticks) == 1
    assert ticks[0][0] == pytest.approx(5.0)


def test_reversed_args_are_swapped():
    assert compute_axis_ticks(X_MAX, -X_MAX) == compute_axis_ticks(-X_MAX, X_MAX)


def test_zero_label_has_no_negative_sign():
    # Integer-step axis.
    z_int = dict(compute_axis_ticks(-X_MAX, X_MAX))
    assert z_int[0.0] == "0"
    # Sub-mm decimal axis.
    z_dec = dict(compute_axis_ticks(0.0, 0.5))
    assert not z_dec[0.0].startswith("-")


def test_target_ticks_override_increases_density():
    sparse = compute_axis_ticks(0.0, 50.0, target_ticks=3)
    dense = compute_axis_ticks(0.0, 50.0, target_ticks=12)
    assert len(dense) > len(sparse)


# --- Z-axis short-span legibility (lever 1: endpoints + zero) ---------------
def test_z_small_span_collapses_to_endpoints():
    # Surface case: ~8 mm relief resting on the stage -> just "0" and "8".
    assert compute_z_ticks(0.0, 8.0) == [(0.0, "0"), (8.0, "8")]


def test_z_small_span_grid_case_two_labels():
    # Grid-alone Z 0..10 mm: 2 endpoints, no intermediate stacking.
    assert compute_z_ticks(0.0, 10.0) == [(0.0, "0"), (10.0, "10")]


def test_z_small_span_includes_zero_when_strictly_inside():
    ticks = compute_z_ticks(-3.0, 5.0)
    assert ticks == [(-3.0, "-3"), (0.0, "0"), (5.0, "5")]


def test_z_small_span_submm_decimal_labels():
    assert compute_z_ticks(0.0, 0.5) == [(0.0, "0.0"), (0.5, "0.5")]


def test_z_large_span_uses_nice_step_ticks():
    # >= 15 mm span -> normal nice-step ticks (more than the 2-3 endpoints).
    ticks = compute_z_ticks(0.0, 40.0)
    assert ticks == compute_axis_ticks(0.0, 40.0, target_ticks=4)
    assert len(ticks) > 3


def test_z_span_threshold_boundary():
    # Just under threshold -> endpoints; at/over -> nice ticks.
    assert len(compute_z_ticks(0.0, 14.0)) == 2
    assert len(compute_z_ticks(0.0, 20.0)) > 2


def test_z_degenerate_single_tick():
    assert compute_z_ticks(0.0, 0.0) == [(0.0, "0")]


# ---------------------------------------------------------------------------
# GL-assembly tests (need a QApplication for GLTextItem's QFont).
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_grid_builds_one_label_per_tick(qapp):
    grid = CoordinateGrid(SHAPE, PS, z_min_mm=0.0, z_max_mm=10.0)
    expected = (
        len(compute_axis_ticks(-X_MAX, X_MAX))
        + len(compute_axis_ticks(-Y_MAX, Y_MAX))
        + len(compute_z_ticks(0.0, 10.0))
    )
    assert len(grid.label_items) == expected
    # Every label carries non-empty text (legibility precondition).
    assert all(item.text for item in grid.label_items)


def test_label_color_and_gloptions_are_deterministic(qapp):
    """Labels must use the explicit opaque near-white color and a
    non-additive glOptions chosen for legibility against the dark bg —
    locks the ADD-TO-SCOPE legibility decision against regressions.

    GLTextItem.setData stores `color` as a QColor (via mkColor), so compare
    via getRgb(). The non-additive glOptions choice is locked at the module
    constant; the rendered legibility itself is verified by the grid smoke
    screenshot.
    """
    from gui.coordinate_grid import _LABEL_COLOR, _LABEL_GLOPTIONS

    grid = CoordinateGrid(SHAPE, PS, z_min_mm=0.0, z_max_mm=10.0)
    label = grid.label_items[0]
    assert label.color.getRgb() == _LABEL_COLOR
    assert label.color.getRgb()[3] == 255  # opaque
    assert _LABEL_GLOPTIONS != "additive"


def test_set_z_extent_rebuilds_z_labels(qapp):
    grid = CoordinateGrid(SHAPE, PS, z_min_mm=0.0, z_max_mm=10.0)
    n_xy = len(compute_axis_ticks(-X_MAX, X_MAX)) + len(compute_axis_ticks(-Y_MAX, Y_MAX))
    n_initial = len(grid.label_items)
    assert n_initial == n_xy + len(compute_z_ticks(0.0, 10.0))

    grid.set_z_extent(0.0, 0.5)
    new_z = compute_z_ticks(0.0, 0.5)
    z_labels = [it.text for it in grid.label_items[-len(new_z):]]
    # Z group rebuilt to the new range; XY labels unchanged.
    assert z_labels == [lbl for _, lbl in new_z]
    assert len(grid.label_items) == n_xy + len(new_z)


def test_flat_z_range_no_crash(qapp):
    """Flat mode: z_min == z_max must not divide-by-zero in grid spacing or
    Z-tick computation; a single Z label is produced."""
    grid = CoordinateGrid(SHAPE, PS, z_min_mm=0.0, z_max_mm=0.0)
    z_labels = compute_z_ticks(0.0, 0.0)
    assert len(z_labels) == 1
    # Total = XY ticks + 1 Z tick; construction succeeded.
    n_xy = len(compute_axis_ticks(-X_MAX, X_MAX)) + len(compute_axis_ticks(-Y_MAX, Y_MAX))
    assert len(grid.label_items) == n_xy + 1


def test_add_to_view_adds_all_items(qapp):
    import pyqtgraph.opengl as gl

    view = gl.GLViewWidget()
    grid = CoordinateGrid(SHAPE, PS, z_min_mm=0.0, z_max_mm=10.0)
    grid.add_to(view)
    # Every grid item is now a child of the view.
    for item in grid.items():
        assert item in view.items


def test_set_z_extent_swaps_items_in_attached_view(qapp):
    import pyqtgraph.opengl as gl

    view = gl.GLViewWidget()
    grid = CoordinateGrid(SHAPE, PS, z_min_mm=0.0, z_max_mm=10.0)
    grid.add_to(view)
    old_z_labels = list(grid._z_label_items)

    grid.set_z_extent(0.0, 0.5)

    # Old Z labels removed from the view, new ones present.
    for old in old_z_labels:
        assert old not in view.items
    for new in grid._z_label_items:
        assert new in view.items
