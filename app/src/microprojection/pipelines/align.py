"""Projector-camera alignment.

Rectifies the projection to the camera: clips it to the camera-visible region,
recenters it on the camera frame center (the alignment crosshair), and stretches
it horizontally to undo the camera's viewing angle.

The camera is telecentric (orthographic), so viewing the plane at a horizontal
angle theta compresses the scene uniformly by cos(theta) along the horizontal
axis - a pure affine scale, no perspective keystone. So a square projected box
images as a rectangle of aspect cos(theta), and the fix is to pre-stretch the
projection horizontally by 1/cos(theta).

Procedure:
1. Project a centered square box; if the camera sees it touching a frame border,
   shrink it and retry until it sits fully inside the frame (so its full extent,
   hence its true width and height in the camera, can be measured).
2. From the camera box: aspect = width/height = cos(theta) -> the horizontal
   angle; box center vs frame center -> the recentering offset; box size in
   camera vs projector pixels -> the projector<->camera scale.
3. Build an affine warp (horizontal stretch 1/cos(theta) about the projector
   center, plus the recentering translation) and a clip box at the warped field,
   apply them to the projector, and project a crosshair as confirmation.

Reports the measured horizontal angle (emitted on ``angleMeasured`` and in the
status line / bottom console bar).

Assumes the projector is roughly normal to the plane with square pixels, square
camera pixels, and that the only misalignment is the horizontal viewing angle
plus a translation (no rotation, no vertical tilt). A real mount needs a hardware
run to confirm the sign and magnitude.
"""
from __future__ import annotations

import math
import os

import numpy as np
from PySide6.QtCore import Signal

from microprojection.patterns import crosshair, solid_box
from microprojection.pipelines.base import CapturePipeline
from microprojection.pipelines.frame_io import save_frame


class AlignProjectionPipeline(CapturePipeline):
    # Measured horizontal viewing angle, in degrees.
    angleMeasured = Signal(float)

    def __init__(self, camera, projector_window, settings, output_dir, *,
                 iterations: int = 16, level: int = 255,
                 bright_fraction: float = 0.4, edge_fraction: float = 0.05,
                 start_fraction: float = 0.8, min_side_px: int = 64, parent=None):
        super().__init__(camera, projector_window, settings, output_dir,
                         parent=parent)
        self._iterations = max(1, int(iterations))
        self._level = level
        self._bright_fraction = bright_fraction
        self._edge_fraction = edge_fraction
        self._start_fraction = start_fraction
        self._min_side_px = min_side_px
        self._side = 0.0
        self._step = 0.0
        # Last measurement from a fully-visible box, used by finalize().
        self._meas: dict | None = None

    @property
    def total(self) -> int:
        return self._iterations

    def pattern_for(self, i: int):
        if i == 0:
            # Make sure no prior correction skews the measurement.
            self._projector_window.set_warp(None, None)
            self._side = min(self.width, self.height) * self._start_fraction
            self._step = max(4.0, min(self.width, self.height) / 20.0)
        return solid_box(self.width, self.height, self._centered_box(),
                         level=self._level)

    def handle_frame(self, i: int, frame) -> None:
        image = np.asarray(frame.image)
        save_frame(os.path.join(self._output_dir, f"frame_{i:02d}.png"), image)

        mask = self._bright_mask(image)
        if float(mask.mean()) < 0.005:
            return  # nothing projected yet (settling)

        h_cam, w_cam = mask.shape[:2]
        ys, xs = np.where(mask)
        if xs.size == 0:
            return
        bx0, bx1 = int(xs.min()), int(xs.max())
        by0, by1 = int(ys.min()), int(ys.max())

        if self._touches_border(mask):
            # Box spills past the frame; shrink it so its full extent is visible.
            self._side = max(self._min_side_px, self._side - self._step)
            return

        # Fully visible: record the box geometry in camera pixels.
        self._meas = {
            "w_cam": (bx1 - bx0 + 1),
            "h_cam": (by1 - by0 + 1),
            "cx": (bx0 + bx1) / 2.0,
            "cy": (by0 + by1) / 2.0,
            "frame_w": w_cam,
            "frame_h": h_cam,
            "side_proj": self._side,
        }

    def finalize(self) -> None:
        if self._meas is None:
            self.status.emit("Alignment failed: the projected box never sat "
                             "fully inside the camera frame.")
            return
        m = self._meas
        # Telecentric horizontal compression: a square projector box images with
        # aspect = width/height = cos(theta). Clamp: >1 is non-physical for a
        # horizontal tilt (would mean vertical compression / a bad assumption).
        aspect = m["w_cam"] / m["h_cam"]
        aspect = min(max(aspect, 1e-3), 1.0)
        theta = math.degrees(math.acos(aspect))

        # Recenter the field on the camera center (the crosshair).
        dx_cam = m["frame_w"] / 2.0 - m["cx"]
        dy_cam = m["frame_h"] / 2.0 - m["cy"]
        # Camera pixels per projector pixel, from the measured box.
        sx = m["w_cam"] / m["side_proj"]
        sy = m["h_cam"] / m["side_proj"]
        tx = dx_cam / sx if sx else 0.0
        ty = dy_cam / sy if sy else 0.0

        # Horizontal stretch about the projector center to undo the compression.
        stretch = 1.0 / aspect
        cx_proj = self.width / 2.0
        warp = np.array([[stretch, 0.0, cx_proj * (1.0 - stretch) + tx],
                         [0.0, 1.0, ty]], dtype=np.float64)
        clip = self._warped_clip(warp)

        self._projector_window.set_warp(warp, clip)
        # Project a crosshair through the correction as visual confirmation.
        self._projector_window.update_pattern(crosshair(self.width, self.height))

        self._write_report(theta, stretch, tx, ty, clip)
        self.angleMeasured.emit(theta)
        self.status.emit(
            f"Projection aligned: horizontal angle {theta:.1f} deg, "
            f"stretch {stretch:.3f}x, recenter ({tx:+.0f}, {ty:+.0f}) px."
        )

    # Geometry and detection helpers.

    def _centered_box(self):
        half = self._side / 2.0
        cx, cy = self.width / 2.0, self.height / 2.0
        return (cx - half, cy - half, cx + half, cy + half)

    def _warped_clip(self, warp: np.ndarray):
        """Clip box = where the visible square lands after the warp, clamped to
        the projector. Keeps the corrected projection within the aligned region."""
        x0, y0, x1, y1 = self._centered_box()
        corners = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]],
                           dtype=np.float64)
        pts = (warp @ corners.T).T  # 4x2 in projector pixels
        nx0 = int(max(0, math.floor(pts[:, 0].min())))
        ny0 = int(max(0, math.floor(pts[:, 1].min())))
        nx1 = int(min(self.width, math.ceil(pts[:, 0].max())))
        ny1 = int(min(self.height, math.ceil(pts[:, 1].max())))
        return (nx0, ny0, nx1, ny1)

    def _bright_mask(self, image: np.ndarray) -> np.ndarray:
        img = image
        if img.ndim == 3:
            img = img.mean(axis=2)
        if img.dtype == np.uint16:
            maxval = 65535.0
        elif img.dtype == np.uint8:
            maxval = 255.0
        else:
            maxval = float(img.max()) or 1.0
        return img.astype(np.float64) / maxval >= self._bright_fraction

    def _touches_border(self, mask: np.ndarray) -> bool:
        h, w = mask.shape[:2]
        s = max(2, min(h, w) // 200)
        f = self._edge_fraction
        return (float(mask[:, :s].mean()) > f or float(mask[:, -s:].mean()) > f
                or float(mask[:s, :].mean()) > f or float(mask[-s:, :].mean()) > f)

    def _write_report(self, theta, stretch, tx, ty, clip) -> None:
        lines = [
            "Projector-camera alignment",
            f"projector resolution: {self.width} x {self.height}",
            f"camera frame: {self._meas['frame_w']} x {self._meas['frame_h']}",
            "",
            f"measured square box in camera: {self._meas['w_cam']} x "
            f"{self._meas['h_cam']} px (aspect {self._meas['w_cam'] / self._meas['h_cam']:.4f})",
            f"horizontal viewing angle: {theta:.2f} deg",
            "",
            "applied correction (affine on the projected pattern):",
            f"  horizontal stretch: {stretch:.4f}x",
            f"  recenter translation: ({tx:+.1f}, {ty:+.1f}) px",
            f"  clip box (x0, y0, x1, y1): {clip}",
        ]
        path = os.path.join(self._output_dir, "alignment.txt")
        with open(path, "w", encoding="ascii") as handle:
            handle.write("\n".join(lines) + "\n")
