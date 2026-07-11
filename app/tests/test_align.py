"""Alignment warp: recentering, 1/cos(theta) stretch, and clipping."""
import numpy as np
import pytest

from backend.align import apply_warp, build_warp

PROJ = (1140, 912)
FOV = (200, 150, 600, 450)  # x, y, w, h -> center (500, 375)


def test_theta_zero_is_pure_recenter():
    m, clip = build_warp(*PROJ, FOV, 0.0)
    np.testing.assert_allclose(m, [[1, 0, 500 - 570], [0, 1, 375 - 456]])
    assert clip == (200, 150, 800, 600)


def test_stretch_is_inverse_cos_about_fov_center():
    m, _ = build_warp(*PROJ, FOV, 60.0)
    assert m[0, 0] == pytest.approx(2.0)
    # The pattern center lands on the FOV center regardless of theta.
    center = np.array([570.0, 456.0, 1.0])
    np.testing.assert_allclose(m @ center, [500.0, 375.0])


def test_extreme_theta_is_clamped():
    m, _ = build_warp(*PROJ, FOV, 89.99)
    assert np.isfinite(m).all() and m[0, 0] <= 1000.0


def test_apply_warp_recenters_and_clips():
    pytest.importorskip("cv2")
    w, h = PROJ
    pattern = np.zeros((h, w), dtype=np.uint8)
    pattern[h // 2 - 4: h // 2 + 4, w // 2 - 4: w // 2 + 4] = 255  # center dot
    m, clip = build_warp(w, h, FOV, 0.0)
    out = apply_warp(pattern, m, clip, PROJ)
    assert out.shape == (h, w)
    assert out[375, 500] == 255          # dot moved to the FOV center
    assert out[h // 2, w // 2] == 0      # and away from the projector center
    assert out[:150, :].max() == 0       # nothing outside the clip box


def test_apply_warp_resizes_foreign_resolution():
    pytest.importorskip("cv2")
    m, clip = build_warp(*PROJ, FOV, 0.0)
    small = np.full((228, 285), 200, dtype=np.uint8)  # quarter resolution
    out = apply_warp(small, m, clip, PROJ)
    assert out.shape == (PROJ[1], PROJ[0])
    assert out[375, 500] == 200
