"""The pattern library and its pane: generators produce the projector-shaped
frames they claim, the file loader letterboxes correctly, and the pane's
selection drives which knobs apply and what gets projected.
"""
from __future__ import annotations

import numpy as np
import pytest

from backend import patterns


# -- generators -----------------------------------------------------------------


@pytest.mark.parametrize("p", patterns.PATTERNS, ids=lambda p: p.key)
def test_every_builtin_generates_projector_frames(p):
    image = patterns.generate(p.key, width=228, height=190)
    assert image.shape == (190, 228)
    assert image.dtype == np.uint8


def test_solids_and_ramp_levels():
    assert patterns.generate("solid_white", 64, 32).min() == 255
    assert patterns.generate("solid_black", 64, 32).max() == 0
    assert patterns.generate("solid_gray", 64, 32).mean() == 128
    ramp = patterns.generate("ramp_h", 256, 8)
    assert ramp[0, 0] == 0 and ramp[0, -1] == 255
    assert (ramp[0] == ramp[-1]).all()  # constant down the height


def test_fringe_orientations():
    v = patterns.generate("fringe_v", width=200, height=100, n_periods=4.0)
    h = patterns.generate("fringe_h", width=200, height=100, n_periods=4.0)
    assert (v[0] == v[-1]).all()        # vertical: rows identical
    assert (h[:, 0] == h[:, -1]).all()  # horizontal: columns identical
    # 4 periods -> the dominant FFT bin along the varying axis is 4
    spectrum = np.abs(np.fft.rfft(v[0].astype(float) - v[0].mean()))
    assert spectrum.argmax() == 4
    spectrum = np.abs(np.fft.rfft(h[:, 0].astype(float) - h[:, 0].mean()))
    assert spectrum.argmax() == 4


def test_checkerboard_alternates_at_pitch():
    board = patterns.generate("checkerboard", width=64, height=64, pitch_px=16)
    assert board[0, 0] == 255
    assert board[0, 16] == 0     # next cell across flips
    assert board[16, 16] == 255  # diagonal neighbor flips back
    assert set(np.unique(board)) == {0, 255}


def test_grid_lines_at_pitch():
    grid = patterns.generate("grid", width=64, height=64, pitch_px=16)
    assert (grid[:, 0] == 255).all() and (grid[0, :] == 255).all()  # lines
    assert grid[8, 8] == 0  # cell interior stays black


def test_crosshair_marks_center_only():
    cross = patterns.generate("crosshair", width=101, height=51)
    assert (cross[25, :] == 255).all() and (cross[:, 50] == 255).all()
    assert cross[0, 0] == 0


def test_image_pattern_letterboxes(tmp_path):
    import cv2

    # A 2:1 white image into a square field: white band, black bars above/below.
    src = np.full((50, 100), 255, dtype=np.uint8)
    path = tmp_path / "pattern.png"
    assert cv2.imwrite(str(path), src)
    image = patterns.generate("image", width=80, height=80, path=path)
    assert image.shape == (80, 80)
    assert (image[40, :] == 255).all()  # the image band
    assert (image[0, :] == 0).all() and (image[-1, :] == 0).all()  # letterbox


def test_image_pattern_requires_path_and_readable_file(tmp_path):
    with pytest.raises(ValueError, match="needs a file path"):
        patterns.generate("image")
    with pytest.raises(ValueError, match="could not read"):
        patterns.generate("image", path=tmp_path / "missing.png")


def test_unknown_pattern_raises():
    with pytest.raises(ValueError, match="unknown pattern"):
        patterns.generate("plaid")


# -- the pane ---------------------------------------------------------------------


def test_pane_lists_builtins_and_defaults_to_first(qapp):
    from ui.patterns import PatternsPane

    pane = PatternsPane()
    assert pane.pattern_list.count() == len(patterns.PATTERNS)
    key, params = pane.selected_pattern()
    assert key == patterns.PATTERNS[0].key
    assert params == {"n_periods": 8.0}  # fringe_v uses only the period knob


def test_pane_knobs_follow_selection(qapp):
    from ui.patterns import PatternsPane

    pane = PatternsPane()
    keys = [p.key for p in patterns.PATTERNS]
    pane.pattern_list.setCurrentRow(keys.index("checkerboard"))
    assert not pane.n_periods.isEnabled() and pane.pitch_px.isEnabled()
    key, params = pane.selected_pattern()
    assert key == "checkerboard" and params == {"pitch_px": 64}
    pane.pattern_list.setCurrentRow(keys.index("solid_white"))
    assert not pane.n_periods.isEnabled() and not pane.pitch_px.isEnabled()
    assert pane.selected_pattern() == ("solid_white", {})


def test_pane_add_image_selects_it(qapp, tmp_path):
    from ui.patterns import PatternsPane

    pane = PatternsPane()
    pane.add_image(str(tmp_path / "target.png"))
    key, params = pane.selected_pattern()
    assert key == patterns.IMAGE_KEY
    assert params == {"path": str(tmp_path / "target.png")}
    assert pane.selected_label() == "target.png"


def test_pane_project_button_emits(qapp):
    from ui.patterns import PatternsPane

    pane = PatternsPane()
    fired = []
    pane.project_requested.connect(lambda: fired.append(True))
    pane.project_button.click()
    assert fired == [True]
