"""Projector-camera alignment warp for *viewing* patterns.

Rectifies a projected pattern to the camera: recenters it on the camera's
center, pre-stretches it horizontally by 1/cos(theta) so the telecentric
camera (which compresses the scene by cos(theta) along its tilt direction --
a pure affine scale, no perspective keystone) sees the correct aspect, and
clips it to the camera-visible region so no light lands outside the frame.

Inputs come from the app's own measurements, not from a box-aspect estimate
(the method calibrate.py implements only as a cross-check):

* theta -- the camera angle from the phase-gradient calibration
  (persisted as calibration/theta_phase_deg);
* the camera-visible region -- the FOV box from backend.fov (persisted as
  fov/box, projector pixels). Its center corresponds to the camera frame
  center by construction (the search converges each box edge onto its
  camera border).

Deliberately applied ONLY to pattern-library projections (alignment / focus
/ linearity viewing patterns). Measurement fringes must stay unwarped: the
reconstruction's analytic carrier (reconstruct.carrier_phase, lambda_eq) and
the per-pixel z-sweep calibration assume the unwarped fringe geometry, and a
warp would silently change the effective fringe pitch. The aim guide also
stays unwarped -- it measures where a *known* projector position lands.

Assumes square pixels on both devices and that the misalignment is the
horizontal viewing angle plus a translation (no rotation, no vertical tilt),
matching the rig model in simulation/geometry_constants.py.
"""
from __future__ import annotations

import math

import numpy as np


def build_warp(proj_w: int, proj_h: int, fov_box: tuple[int, int, int, int],
               theta_deg: float) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """The affine warp (2x3) and clip box, both in projector pixels.

    fov_box is (x, y, w, h). The pattern center maps to the FOV box center
    (recentering on the camera), then the horizontal 1/cos(theta) stretch is
    taken about that center so the recentered pattern stretches around the
    camera's own center.
    """
    x, y, w, h = fov_box
    fov_cx, fov_cy = x + w / 2.0, y + h / 2.0
    # Clamp: cos -> 0 blows the stretch up; anything past ~85 deg means a bad
    # theta, not a real mounting.
    cos_t = max(math.cos(math.radians(theta_deg)), 1e-3)
    s = 1.0 / cos_t
    # x' = s*(x - proj_cx) + fov_cx ; y' = (y - proj_cy) + fov_cy
    matrix = np.array(
        [[s, 0.0, fov_cx - s * (proj_w / 2.0)],
         [0.0, 1.0, fov_cy - proj_h / 2.0]], dtype=np.float64)
    clip = (max(0, int(x)), max(0, int(y)),
            min(proj_w, int(x + w)), min(proj_h, int(y + h)))
    return matrix, clip


def apply_warp(pattern: np.ndarray, matrix: np.ndarray,
               clip: tuple[int, int, int, int],
               proj_size: tuple[int, int]) -> np.ndarray:
    """Warp a pattern into projector space and zero everything outside the
    clip box. The pattern is first brought to projector resolution (the
    matrix and clip are in projector pixels)."""
    import cv2

    w, h = proj_size
    img = np.asarray(pattern)
    if img.shape[:2] != (h, w):
        img = cv2.resize(img, (w, h), interpolation=cv2.INTER_NEAREST)
    out = cv2.warpAffine(img, matrix, (w, h), flags=cv2.INTER_LINEAR,
                         borderValue=0)
    x0, y0, x1, y1 = clip
    mask = np.zeros_like(out)
    if x1 > x0 and y1 > y0:
        mask[y0:y1, x0:x1] = out[y0:y1, x0:x1]
    return mask
