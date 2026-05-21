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


def _make_box_stl(
    path: Path,
    sx: float,
    sy: float,
    sz: float,
    center=(0.0, 0.0, 0.0),
) -> Path:
    """Write a closed-solid axis-aligned box STL of size (sx, sy, sz) mm."""
    hx, hy, hz = sx / 2, sy / 2, sz / 2
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


def _make_cube_stl(path: Path, side: float, center=(0.0, 0.0, 0.0)) -> Path:
    """Write a closed-solid cube STL of side `side` mm to `path`."""
    return _make_box_stl(path, side, side, side, center=center)


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
        "STL Browser",
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
    # Sanity: the cached heightmap is the (550, 680) float64 array.
    assert main_window._stl_heightmap.shape == (550, 680)
    assert main_window._stl_heightmap.dtype == np.float64
    # Small part: direct (Stage 4c) path. No Browser-mode state.
    assert main_window._stl_is_browser_mode is False
    assert main_window._stl_full_heightmap is None
    assert main_window._stl_full_origin_mm is None
    assert main_window._stl_fov_origin_mm is None


def test_z_overflow_stl_rejected(main_window, tmp_path, monkeypatch):
    # 130 mm cube: Z = 130 mm exceeds the 120 mm working-volume Z cap.
    # Z-reject branch precedes XY classification — even though X/Y are
    # also too large, the Z check fires first.
    big = _make_cube_stl(tmp_path / "tall.stl", side=130.0)
    prev_idx = main_window.surface_combo.currentIndex()
    _patch_file_dialog(monkeypatch, return_path=str(big))
    warnings = _patch_warning(monkeypatch)

    main_window.surface_combo.setCurrentText(STL_LABEL)

    assert len(warnings) == 1
    assert warnings[0][1] == "STL too tall"
    assert "exceeds the working-volume Z cap" in warnings[0][2]
    assert main_window.surface_combo.currentIndex() == prev_idx
    assert main_window._stl_heightmap is None
    assert main_window._stl_full_heightmap is None
    assert main_window._stl_is_browser_mode is False


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


# ---------------------------------------------------------------------------
# Stage 4d sub-task 2: bbox classification + Browser-mode state.
# ---------------------------------------------------------------------------
def test_browser_mode_populates_full_cache(main_window, tmp_path, monkeypatch):
    # 100 x 80 x 30 mm: XY exceeds working volume (68 x 55), Z fits the
    # 120 mm cap, XY within ABSURDLY_LARGE_MM (272 x 220). -> Browser path.
    stl_path = _make_box_stl(
        tmp_path / "wide.stl", sx=100.0, sy=80.0, sz=30.0,
    )
    _patch_file_dialog(monkeypatch, return_path=str(stl_path))
    _patch_warning(monkeypatch)

    main_window.surface_combo.setCurrentText(STL_LABEL)

    assert main_window._stl_is_browser_mode is True
    assert main_window._stl_full_heightmap is not None
    assert main_window._stl_full_heightmap.shape == (800, 1000)
    assert main_window._stl_full_heightmap.dtype == np.float64
    # FOV slice cached for the math layer; shape stays the canonical FOV.
    assert main_window._stl_heightmap.shape == (550, 680)
    # Centered cube: bbox (-50, +50) x (-40, +40). Origin = bbox min.
    assert main_window._stl_full_origin_mm == (-50.0, -40.0)
    # Centered initial FOV: part center (0, 0) - half-FOV.
    fov_origin = main_window._stl_fov_origin_mm
    assert fov_origin is not None
    assert fov_origin[0] == pytest.approx(-34.0)  # -W_fov/2 * ps
    assert fov_origin[1] == pytest.approx(-27.5)


def test_absurd_xy_rejected(main_window, tmp_path, monkeypatch):
    # 300 x 250 mm: XY beyond ABSURDLY_LARGE_MM (272 x 220), Z fits.
    huge = _make_box_stl(
        tmp_path / "absurd.stl", sx=300.0, sy=250.0, sz=10.0,
    )
    prev_idx = main_window.surface_combo.currentIndex()
    _patch_file_dialog(monkeypatch, return_path=str(huge))
    warnings = _patch_warning(monkeypatch)

    main_window.surface_combo.setCurrentText(STL_LABEL)

    assert len(warnings) == 1
    assert warnings[0][1] == "STL too large"
    assert "exceeds the maximum supported size" in warnings[0][2]
    # Both the part's bbox and the threshold appear in the message so the
    # user can see the gap.
    assert "300.0" in warnings[0][2]
    assert "272" in warnings[0][2]
    assert main_window.surface_combo.currentIndex() == prev_idx
    assert main_window._stl_heightmap is None
    assert main_window._stl_full_heightmap is None
    assert main_window._stl_is_browser_mode is False


def test_browser_to_small_clears_full_cache(
    main_window, tmp_path, monkeypatch,
):
    # Load Browser STL first.
    big = _make_box_stl(tmp_path / "big.stl", sx=100.0, sy=80.0, sz=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(big))
    _patch_warning(monkeypatch)
    main_window.surface_combo.setCurrentText(STL_LABEL)
    assert main_window._stl_is_browser_mode is True
    assert main_window._stl_full_heightmap is not None

    # Re-open file dialog with a small STL via the Change button.
    small = _make_cube_stl(tmp_path / "small.stl", side=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(small))
    main_window.stl_change_button.click()

    # Browser-mode state cleared; small-path state populated.
    assert main_window._stl_is_browser_mode is False
    assert main_window._stl_full_heightmap is None
    assert main_window._stl_full_origin_mm is None
    assert main_window._stl_fov_origin_mm is None
    assert main_window._stl_heightmap is not None
    assert main_window._stl_heightmap.shape == (550, 680)


def test_browser_to_flat_preserves_full_cache(
    main_window, tmp_path, monkeypatch,
):
    # Load Browser STL, then switch dropdown to Flat. Browser cache
    # survives the dropdown change (Stage 4c lifetime rule extends).
    big = _make_box_stl(tmp_path / "big.stl", sx=100.0, sy=80.0, sz=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(big))
    _patch_warning(monkeypatch)
    main_window.surface_combo.setCurrentText(STL_LABEL)
    full_cached = main_window._stl_full_heightmap
    fov_cached = main_window._stl_fov_origin_mm
    assert full_cached is not None

    main_window.surface_combo.setCurrentText("Flat")

    # Browser cache untouched by the dropdown change.
    assert main_window._stl_full_heightmap is full_cached
    assert main_window._stl_fov_origin_mm == fov_cached
    assert main_window._stl_is_browser_mode is True


def test_extract_fov_slice_partial_off_part(main_window):
    """_extract_fov_slice with an origin that pushes the window past
    the full heightmap's edges. In-bounds portion must contain the
    correct values; out-of-bounds portion must be 0.0."""
    # Construct a synthetic 200 x 300 (H x W) full heightmap directly on
    # the MainWindow instance — no STL file needed. Each pixel set to
    # 100.0 mm so off-part 0s are visually distinct.
    full = np.full((200, 300), 100.0, dtype=np.float64)
    main_window._stl_full_heightmap = full
    # Place the (0, 0) pixel at part-local (0.0, 0.0) for clean math.
    main_window._stl_full_origin_mm = (0.0, 0.0)

    # FOV is (550, 680). Origin at (-20, -10) mm in part-local coords:
    # col offset = round((-20 - 0) / 0.1) = -200
    # row offset = round((-10 - 0) / 0.1) = -100
    # The FOV window is [row=-100 .. row=450, col=-200 .. col=480].
    # Overlap with [0..200, 0..300] is [0..200, 0..300] -> covers
    # full[0:200, 0:300] entirely.
    # Mapped to output: out[100:300, 200:500] = full[0:200, 0:300].
    out = main_window._extract_fov_slice((-20.0, -10.0))

    assert out.shape == (550, 680)
    # In-bounds region: out[100:300, 200:500] holds the full's values.
    np.testing.assert_array_equal(out[100:300, 200:500], 100.0)
    # Out-of-bounds: the rest is exact 0.0.
    # Top strip (rows 0..100): all zero.
    np.testing.assert_array_equal(out[:100, :], 0.0)
    # Bottom strip (rows 300..end): all zero.
    np.testing.assert_array_equal(out[300:, :], 0.0)
    # Left strip (cols 0..200): all zero.
    np.testing.assert_array_equal(out[:, :200], 0.0)
    # Right strip (cols 500..end): all zero.
    np.testing.assert_array_equal(out[:, 500:], 0.0)


def test_extract_fov_slice_entirely_off_part(main_window):
    """An origin so far past the part that no overlap exists: all-zero
    output, no exception."""
    main_window._stl_full_heightmap = np.full((50, 50), 7.0, dtype=np.float64)
    main_window._stl_full_origin_mm = (0.0, 0.0)
    # Origin at (+500, +500) mm is wildly past the 5 x 5 mm full
    # heightmap; no overlap.
    out = main_window._extract_fov_slice((500.0, 500.0))
    assert out.shape == (550, 680)
    np.testing.assert_array_equal(out, 0.0)


# ---------------------------------------------------------------------------
# Stage 4d sub-task 3: STL Browser tab state dispatch.
# ---------------------------------------------------------------------------
def test_browser_tab_present_and_initial_placeholder(main_window):
    """Tab exists at construction; initial state is placeholder."""
    tabs = main_window.right_pane_tabs
    assert tabs.count() == 3
    assert tabs.tabText(2) == "STL Browser"
    assert main_window.stl_browser.is_showing_panels is False


def test_switching_to_flat_keeps_placeholder(main_window):
    """Dropdown change from Gaussian to Flat doesn't flip panel state."""
    main_window.surface_combo.setCurrentText("Flat")
    assert main_window.stl_browser.is_showing_panels is False


def test_small_stl_load_shows_placeholder(main_window, tmp_path, monkeypatch):
    """A small STL goes through the direct path; Browser tab stays in
    placeholder."""
    stl_path = _make_cube_stl(tmp_path / "small.stl", side=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(stl_path))
    _patch_warning(monkeypatch)

    main_window.surface_combo.setCurrentText(STL_LABEL)

    assert main_window.stl_browser.is_showing_panels is False


def test_oversized_stl_load_shows_panels(main_window, tmp_path, monkeypatch):
    """A Browser-mode STL load flips the panel state to visible."""
    big = _make_box_stl(tmp_path / "big.stl", sx=100.0, sy=80.0, sz=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(big))
    _patch_warning(monkeypatch)

    main_window.surface_combo.setCurrentText(STL_LABEL)

    assert main_window.stl_browser.is_showing_panels is True


def test_browser_to_flat_dropdown_keeps_panels(
    main_window, tmp_path, monkeypatch,
):
    """Dropdown change Browser-STL -> Flat preserves panels (Browser
    cache survives the dropdown switch per sub-task 2's lifetime rule)."""
    big = _make_box_stl(tmp_path / "big.stl", sx=100.0, sy=80.0, sz=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(big))
    _patch_warning(monkeypatch)
    main_window.surface_combo.setCurrentText(STL_LABEL)
    assert main_window.stl_browser.is_showing_panels is True

    main_window.surface_combo.setCurrentText("Flat")

    assert main_window.stl_browser.is_showing_panels is True


def test_browser_to_small_stl_shows_placeholder(
    main_window, tmp_path, monkeypatch,
):
    """Loading a small STL after a Browser STL clears Browser cache and
    flips the panel state back to placeholder."""
    big = _make_box_stl(tmp_path / "big.stl", sx=100.0, sy=80.0, sz=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(big))
    _patch_warning(monkeypatch)
    main_window.surface_combo.setCurrentText(STL_LABEL)
    assert main_window.stl_browser.is_showing_panels is True

    small = _make_cube_stl(tmp_path / "small.stl", side=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(small))
    main_window.stl_change_button.click()

    assert main_window.stl_browser.is_showing_panels is False


# ---------------------------------------------------------------------------
# Stage 4d sub-task 4: Browser Panels 1 and 3 rendered content.
# ---------------------------------------------------------------------------
def test_browser_load_constructs_both_panel_items(
    main_window, tmp_path, monkeypatch,
):
    """A Browser-mode STL load populates Panel 1 (whole-STL) and
    Panel 3 (windowed slice) GLSurfacePlotItems."""
    big = _make_box_stl(tmp_path / "big.stl", sx=100.0, sy=80.0, sz=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(big))
    _patch_warning(monkeypatch)

    main_window.surface_combo.setCurrentText(STL_LABEL)

    browser = main_window.stl_browser
    assert browser.has_whole_stl_content is True
    assert browser.has_windowed_slice is True


def test_small_stl_load_does_not_populate_browser_panels(
    main_window, tmp_path, monkeypatch,
):
    """A direct-path STL load does NOT populate Browser panels —
    Browser-mode state stays empty."""
    small = _make_cube_stl(tmp_path / "small.stl", side=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(small))
    _patch_warning(monkeypatch)

    main_window.surface_combo.setCurrentText(STL_LABEL)

    browser = main_window.stl_browser
    assert browser.has_whole_stl_content is False
    assert browser.has_windowed_slice is False


def test_browser_load_idempotent_no_item_accumulation(
    main_window, tmp_path, monkeypatch,
):
    """Repeated Browser STL loads reuse the same GLSurfacePlotItem
    instances — items don't accumulate in the GLViewWidget."""
    big1 = _make_box_stl(tmp_path / "big1.stl", sx=100.0, sy=80.0, sz=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(big1))
    _patch_warning(monkeypatch)
    main_window.surface_combo.setCurrentText(STL_LABEL)

    browser = main_window.stl_browser
    item1_whole = browser._whole_stl_item
    item1_windowed = browser._windowed_item
    assert item1_whole is not None
    assert item1_windowed is not None

    # Load a second oversized STL via the Change button.
    big2 = _make_box_stl(tmp_path / "big2.stl", sx=120.0, sy=90.0, sz=25.0)
    _patch_file_dialog(monkeypatch, return_path=str(big2))
    main_window.stl_change_button.click()

    # Same item instances — reused, not stacked.
    assert browser._whole_stl_item is item1_whole
    assert browser._windowed_item is item1_windowed
    # And the GLViewWidget child item counts haven't doubled.
    assert browser._whole_stl_view.items.count(item1_whole) == 1
    assert browser._windowed_view.items.count(item1_windowed) == 1


def test_update_whole_stl_resets_camera_distance(main_window, tmp_path):
    """Panel 1's camera distance scales to the part bbox on each
    update_whole_stl call."""
    hm_small = np.zeros((400, 500), dtype=np.float64)  # 40 x 50 mm at 0.1 px
    main_window.stl_browser.update_whole_stl(hm_small, 0.1)
    d_small = main_window.stl_browser._whole_stl_view.cameraParams()["distance"]

    hm_big = np.zeros((2000, 2500), dtype=np.float64)  # 200 x 250 mm
    main_window.stl_browser.update_whole_stl(hm_big, 0.1)
    d_big = main_window.stl_browser._whole_stl_view.cameraParams()["distance"]

    # 1.5 * max(W*ps, H*ps): small=1.5*50=75, big=1.5*250=375.
    assert d_small == 75.0
    assert d_big == 375.0


def test_update_windowed_slice_preserves_camera_pose(main_window, tmp_path):
    """Panel 3's camera pose is preserved across update_windowed_slice
    calls — the drag handler must not cause view re-jolt."""
    hm = np.zeros((550, 680), dtype=np.float64)
    browser = main_window.stl_browser
    browser.update_windowed_slice(hm, 0.1)

    # User pans the view (simulated by setCameraPosition).
    browser._windowed_view.setCameraPosition(
        distance=420, elevation=10, azimuth=120,
    )
    params_before = browser._windowed_view.cameraParams().copy()

    # Push a new slice (simulating the drag-update path).
    hm2 = np.full((550, 680), 5.0, dtype=np.float64)
    browser.update_windowed_slice(hm2, 0.1)

    params_after = browser._windowed_view.cameraParams()
    assert params_after["distance"] == params_before["distance"]
    assert params_after["elevation"] == params_before["elevation"]
    assert params_after["azimuth"] == params_before["azimuth"]


# ---------------------------------------------------------------------------
# Stage 4d sub-task 5: minimap + draggable FOV rectangle.
# ---------------------------------------------------------------------------
def test_browser_load_constructs_minimap_and_roi(
    main_window, tmp_path, monkeypatch,
):
    """A Browser-mode STL load populates the minimap ImageItem and
    the FOV RectROI."""
    big = _make_box_stl(tmp_path / "big.stl", sx=100.0, sy=80.0, sz=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(big))
    _patch_warning(monkeypatch)

    main_window.surface_combo.setCurrentText(STL_LABEL)

    browser = main_window.stl_browser
    assert browser.has_minimap_content is True
    assert browser._minimap_roi is not None


def test_minimap_roi_initial_position_matches_fov_origin(
    main_window, tmp_path, monkeypatch,
):
    """After a Browser load, the FOV rectangle's pos() matches
    MainWindow's _stl_fov_origin_mm cache."""
    big = _make_box_stl(tmp_path / "big.stl", sx=100.0, sy=80.0, sz=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(big))
    _patch_warning(monkeypatch)

    main_window.surface_combo.setCurrentText(STL_LABEL)

    roi_pos = main_window.stl_browser._minimap_roi.pos()
    fov_origin = main_window._stl_fov_origin_mm
    assert float(roi_pos[0]) == pytest.approx(fov_origin[0])
    assert float(roi_pos[1]) == pytest.approx(fov_origin[1])


def test_minimap_roi_size_is_fov_size(main_window, tmp_path, monkeypatch):
    """The FOV rectangle is sized to the hardware FOV (68 x 55 mm) at
    SURFACE_PIXEL_SIZE_MM=0.1, NOT scaled to the part bbox."""
    # Load a part that's much larger than the FOV so a part-scaled
    # rectangle would be obviously wrong.
    big = _make_box_stl(tmp_path / "big.stl", sx=200.0, sy=160.0, sz=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(big))
    _patch_warning(monkeypatch)

    main_window.surface_combo.setCurrentText(STL_LABEL)

    roi_size = main_window.stl_browser._minimap_roi.size()
    # W_fov = 680 * 0.1 = 68 mm, H_fov = 550 * 0.1 = 55 mm.
    assert float(roi_size[0]) == pytest.approx(68.0)
    assert float(roi_size[1]) == pytest.approx(55.0)


def test_drag_updates_fov_origin_and_windowed_slice(
    main_window, tmp_path, monkeypatch,
):
    """Programmatically moving the ROI fires fov_dragged, which
    updates _stl_fov_origin_mm + _stl_heightmap and pushes a new
    slice to Panel 3's GLSurfacePlotItem."""
    big = _make_box_stl(tmp_path / "big.stl", sx=100.0, sy=80.0, sz=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(big))
    _patch_warning(monkeypatch)
    main_window.surface_combo.setCurrentText(STL_LABEL)

    initial_origin = main_window._stl_fov_origin_mm
    initial_heightmap = main_window._stl_heightmap

    # Move the ROI to a clearly different in-part position. The cube
    # bbox is (-50, +50) x (-40, +40); shift the FOV origin -10 mm in X.
    new_x = initial_origin[0] - 10.0
    new_y = initial_origin[1]
    main_window.stl_browser._minimap_roi.setPos((new_x, new_y))

    # MainWindow's cache reflects the new origin.
    assert main_window._stl_fov_origin_mm[0] == pytest.approx(new_x)
    assert main_window._stl_fov_origin_mm[1] == pytest.approx(new_y)
    # And the cached slice is a different array than the initial one
    # (the actual heightmap content differs at the new origin because
    # the cube's edge is partially clipped).
    assert main_window._stl_heightmap is not initial_heightmap
    # Panel 3's GLSurfacePlotItem exists and has been re-fed.
    assert main_window.stl_browser._windowed_item is not None


def test_drag_does_not_update_lab_view(main_window, tmp_path, monkeypatch):
    """Drag updates Panel 3 only — the lab view's SurfacePreview keeps
    its committed-FOV heightmap. Sub-task 6 will wire the commit."""
    big = _make_box_stl(tmp_path / "big.stl", sx=100.0, sy=80.0, sz=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(big))
    _patch_warning(monkeypatch)
    main_window.surface_combo.setCurrentText(STL_LABEL)

    # Lab view's last-rendered heightmap (cached on view_3d).
    lab_heightmap_before = main_window.view_3d._last_heightmap

    # Drag the ROI off-center.
    initial_origin = main_window._stl_fov_origin_mm
    new_origin = (initial_origin[0] - 20.0, initial_origin[1] + 5.0)
    main_window.stl_browser._minimap_roi.setPos(new_origin)

    # Lab view's heightmap is the same array — not updated by drag.
    assert main_window.view_3d._last_heightmap is lab_heightmap_before


def test_drag_off_part_renders_bare_stage(main_window, tmp_path, monkeypatch):
    """Drag the FOV to a position where it extends past the part's
    bbox edge. The new slice has 0.0 (bare-stage) in the off-part
    region; the in-part region carries real heightmap values."""
    # 100x80 cube at center: bbox X in [-50, +50], Y in [-40, +40].
    big = _make_box_stl(tmp_path / "big.stl", sx=100.0, sy=80.0, sz=30.0)
    _patch_file_dialog(monkeypatch, return_path=str(big))
    _patch_warning(monkeypatch)
    main_window.surface_combo.setCurrentText(STL_LABEL)

    # FOV is 68 x 55 mm. Drag origin to (+40, -27.5) so the FOV spans
    # X = [+40, +108]; everything past x_max=+50 is off-part bare stage.
    main_window.stl_browser._minimap_roi.setPos((40.0, -27.5))

    slice_hm = main_window._stl_heightmap
    assert slice_hm.shape == (550, 680)
    # Off-part columns (X > 50): col where x_world = 40 + col*0.1 > 50,
    # i.e. col > 100. Those columns must be exact 0.0.
    np.testing.assert_array_equal(slice_hm[:, 101:], 0.0)
    # The in-part portion contains non-zero values from the cube top.
    in_part = slice_hm[:, :100]
    assert (in_part > 0.0).any(), "in-part region should carry cube-top values"
