"""GUI-level tests for the Stage 4c sub-task 3 STL import flow.

These tests construct a real `MainWindow` and exercise the
dropdown / QFileDialog / Change-button / cache lifecycle paths via
monkeypatched `QFileDialog.getOpenFileName` and `QMessageBox.warning`
so no real dialog ever pops.

Path setup
----------
`conftest.py` puts `src/` on sys.path. `main_window.py` also does
`from src.gui...` imports, which need the repo root on sys.path; the
two lines below add it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox
from stl import mesh as stl_mesh

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from gui.main_window import MainWindow, STL_LABEL  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def main_window(qapp):
    w = MainWindow()
    yield w
    w.close()


def _make_cube_stl(path: Path, side: float, center=(0.0, 0.0, 0.0)) -> Path:
    """Write a closed-solid cube STL of side `side` mm to `path`."""
    hx = hy = hz = side / 2
    cx, cy, cz = center

    def corner(ix, iy, iz):
        return (
            cx + (hx if ix else -hx),
            cy + (hy if iy else -hy),
            cz + (hz if iz else -hz),
        )

    p = {(ix, iy, iz): corner(ix, iy, iz)
         for ix in (0, 1) for iy in (0, 1) for iz in (0, 1)}

    def quad(a, b, c, d):
        return [[p[a], p[b], p[c]], [p[a], p[c], p[d]]]

    tris = []
    tris += quad((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))
    tris += quad((0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0))
    tris += quad((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1))
    tris += quad((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0))
    tris += quad((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0))
    tris += quad((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1))

    data = np.zeros(len(tris), dtype=stl_mesh.Mesh.dtype)
    m = stl_mesh.Mesh(data, remove_empty_areas=False)
    m.vectors[:] = np.asarray(tris, dtype=np.float64)
    m.save(str(path))
    return path


def _patch_file_dialog(monkeypatch, return_path: str) -> list:
    """Patch QFileDialog.getOpenFileName to return `(return_path, "")`.

    Returns a list that records each call's (args, kwargs) — empty if
    the dialog was never invoked.
    """
    calls = []

    def fake(*args, **kwargs):
        calls.append((args, kwargs))
        return (return_path, "")

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(fake))
    return calls


def _patch_warning(monkeypatch) -> list:
    """Patch QMessageBox.warning; return a list of call arg tuples."""
    calls = []

    def fake(*args, **kwargs):
        calls.append(args)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(fake))
    return calls


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------
def test_dropdown_has_three_entries(main_window):
    labels = [
        main_window.surface_combo.itemText(i)
        for i in range(main_window.surface_combo.count())
    ]
    assert labels == ["Flat", "Gaussian", "STL file..."]

    tabs = main_window.right_pane_tabs
    assert [tabs.tabText(i) for i in range(tabs.count())] == [
        "3D Scene",
        "Pipeline Stages",
    ]


def test_cancel_dropdown_reverts(main_window, monkeypatch):
    prev_text = main_window.surface_combo.currentText()
    prev_idx = main_window.surface_combo.currentIndex()
    _patch_file_dialog(monkeypatch, return_path="")  # user "cancels"
    _patch_warning(monkeypatch)

    main_window.surface_combo.setCurrentText(STL_LABEL)

    assert main_window.surface_combo.currentIndex() == prev_idx
    assert main_window.surface_combo.currentText() == prev_text
    assert main_window._stl_heightmap is None
    # Page also reverted to the previous (Gaussian) page, not stuck on STL.
    assert main_window.surface_pages.currentIndex() == prev_idx


def test_successful_load_populates_state(main_window, tmp_path, monkeypatch):
    stl_path = _make_cube_stl(tmp_path / "cube30.stl", side=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(stl_path))
    _patch_warning(monkeypatch)

    main_window.surface_combo.setCurrentText(STL_LABEL)

    assert main_window._stl_heightmap is not None
    assert main_window._stl_filename == "cube30.stl"
    assert main_window._stl_path == stl_path
    assert main_window.stl_filename_label.text() == "STL: cube30.stl"
    assert main_window.stl_inner.currentIndex() == 1  # loaded page
    # Sanity: the cached heightmap is the (480, 640) float64 array.
    assert main_window._stl_heightmap.shape == (480, 640)
    assert main_window._stl_heightmap.dtype == np.float64


def test_oversized_stl_warns_and_reverts(main_window, tmp_path, monkeypatch):
    # 100 mm cube -> X extent 100 > 68 mm limit -> guard rejects.
    big = _make_cube_stl(tmp_path / "huge.stl", side=100.0)
    prev_idx = main_window.surface_combo.currentIndex()
    _patch_file_dialog(monkeypatch, return_path=str(big))
    warnings = _patch_warning(monkeypatch)

    main_window.surface_combo.setCurrentText(STL_LABEL)

    assert len(warnings) == 1
    # warning(parent, title, text) -> args = (parent, title, text)
    assert warnings[0][1] == "STL too large"
    assert "exceeds the working volume" in warnings[0][2]
    assert main_window.surface_combo.currentIndex() == prev_idx
    assert main_window._stl_heightmap is None


def test_cache_hit_no_dialog_on_revisit(main_window, tmp_path, monkeypatch):
    stl_path = _make_cube_stl(tmp_path / "cube30.stl", side=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(stl_path))
    _patch_warning(monkeypatch)

    # First load via dropdown.
    main_window.surface_combo.setCurrentText(STL_LABEL)
    cached = main_window._stl_heightmap
    assert cached is not None

    # Now repatch the dialog to record any further calls.
    second_calls = _patch_file_dialog(monkeypatch, return_path="")

    main_window.surface_combo.setCurrentText("Flat")
    main_window.surface_combo.setCurrentText(STL_LABEL)

    assert second_calls == [], "dialog must not reopen when cache is present"
    assert main_window._stl_heightmap is cached
    assert main_window.stl_inner.currentIndex() == 1


def test_change_button_cancel_keeps_cache(main_window, tmp_path, monkeypatch):
    stl_path = _make_cube_stl(tmp_path / "cube30.stl", side=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(stl_path))
    _patch_warning(monkeypatch)

    main_window.surface_combo.setCurrentText(STL_LABEL)
    cached = main_window._stl_heightmap
    assert cached is not None

    # Change button + canceled dialog: cache stays, dropdown stays on STL.
    _patch_file_dialog(monkeypatch, return_path="")
    main_window.stl_change_button.click()

    assert main_window._stl_heightmap is cached
    assert main_window.surface_combo.currentText() == STL_LABEL
    assert main_window.stl_inner.currentIndex() == 1
