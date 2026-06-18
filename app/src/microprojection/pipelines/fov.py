"""Camera field-of-view identification.

Finds the projector pixel region that lands inside the camera's frame, i.e. the
camera FOV expressed in projector coordinates. The projector draws a filled
bright box; the camera locates it; the box is shrunk to fit until it sits just
inside the camera frame, and the converged box is reported as the FOV.

Each of the four box edges is driven by an independent search. Every iteration
the captured frame is thresholded to a bright mask, and each camera border is
checked: if the projection still spills over that border the box edge is moved
inward, otherwise it is moved outward. Each edge keeps a full-size step until its
clip state first flips (i.e. it has bracketed the FOV boundary); only then does
its step start halving to refine. Halving before bracketing would cap how far an
edge can travel (~2x the initial step), which strands an edge that needs to move
a long way - the bug that left the side edges short of the FOV. After a handful
of iterations every edge settles onto the boundary. The match is then projected
as a hollow outline so the camera sees its own FOV, and the result is saved.

Frames where nothing is projected yet (the projector still settling on the first
box) read as dark and are skipped, so they neither move an edge nor decay a step.

Assumes the projector and camera axes are roughly aligned (no large rotation,
and camera ReverseX/ReverseY off, which are the defaults): camera-left clipping
maps to the projector box's left edge, and so on. A mirrored or strongly rotated
mounting would need an axis-mapping step first.
"""
from __future__ import annotations

import os

import numpy as np

from microprojection.patterns import box_outline, solid_box
from microprojection.pipelines.base import CapturePipeline
from microprojection.pipelines.frame_io import save_frame, save_png


class FovPipeline(CapturePipeline):
    # Box edges and the camera border each maps to (border, inward sign): moving
    # an edge "inward" shrinks the box. left/top grow their coordinate inward;
    # right/bottom shrink theirs.
    _EDGES = (("left", 0, +1), ("right", 2, -1), ("top", 1, +1), ("bottom", 3, -1))

    def __init__(self, camera, projector_window, settings, output_dir, *,
                 iterations: int = 32, level: int = 255,
                 bright_fraction: float = 0.4, edge_fraction: float = 0.05,
                 min_box_px: int = 16, parent=None):
        super().__init__(camera, projector_window, settings, output_dir,
                         parent=parent)
        self._iterations = max(1, int(iterations))
        self._level = level
        # A camera pixel counts as lit if it reaches this fraction of full scale.
        self._bright_fraction = bright_fraction
        # A border counts as still-clipped if this fraction of its edge slab is lit.
        self._edge_fraction = edge_fraction
        # Below this lit fraction the frame is treated as un-projected (settling)
        # and skipped rather than acted on.
        self._dark_fraction = 0.005
        self._min_box_px = min_box_px
        # (x0, y0, x1, y1) in projector pixels; initialised on the first frame
        # once the projector size is known.
        self._box: list[float] | None = None
        # Per-edge search step and previous clip state, for bracket-then-refine.
        self._edge_step: dict[str, float] = {}
        self._prev_clip: dict[str, bool | None] = {}

    @property
    def total(self) -> int:
        return self._iterations

    def pattern_for(self, i: int):
        if i == 0:
            # Start from the full projector area and a coarse search step.
            self._box = [0.0, 0.0, float(self.width), float(self.height)]
            step0 = max(2.0, min(self.width, self.height) / 4.0)
            self._edge_step = {name: step0 for name, _, _ in self._EDGES}
            self._prev_clip = {name: None for name, _, _ in self._EDGES}
        return solid_box(self.width, self.height, self._box, level=self._level)

    def handle_frame(self, i: int, frame) -> None:
        image = np.asarray(frame.image)
        # Keep the raw capture for inspection.
        save_frame(os.path.join(self._output_dir, f"frame_{i:02d}.png"), image)

        mask = self._bright_mask(image)
        if float(mask.mean()) < self._dark_fraction:
            # Nothing projected yet (still settling): don't move any edge or
            # decay any step, just keep the same box and try the next frame.
            return

        clipped = self._clipped_sides(mask)
        box = list(self._box)
        for name, idx, inward in self._EDGES:
            c = clipped[name]
            prev = self._prev_clip[name]
            # Halve this edge's step only once it has bracketed the boundary (its
            # clip state flipped); until then keep the full step so it can travel
            # as far as the FOV boundary needs, however distant.
            if prev is not None and prev != c:
                self._edge_step[name] = max(1.0, self._edge_step[name] / 2.0)
            self._prev_clip[name] = c
            step = self._edge_step[name]
            # Inward (shrink) while still clipped; outward (toward full) once not.
            box[idx] += inward * step if c else -inward * step
        self._box = self._sanitize_box(*box)

    def finalize(self) -> None:
        x0, y0, x1, y1 = (int(round(v)) for v in self._box)
        w, h = x1 - x0, y1 - y0
        # Show the match on the projector as a hollow outline (so the operator
        # sees the camera FOV without flooding the scene with light), and save
        # both the projector-space view and a report.
        outline = box_outline(self.width, self.height, self._box, level=self._level)
        self._projector_window.update_pattern(outline)
        save_png(os.path.join(self._output_dir, "fov_outline.png"), outline)
        save_png(os.path.join(self._output_dir, "fov_solid.png"),
                 solid_box(self.width, self.height, self._box, level=self._level))
        self._write_report(x0, y0, w, h)
        self.status.emit(
            f"Camera FOV in projector pixels: {w} x {h} at ({x0}, {y0}). "
            f"Outline projected; results saved."
        )

    # Detection.

    def _bright_mask(self, image: np.ndarray) -> np.ndarray:
        """Boolean mask of lit camera pixels, thresholded at a fraction of full
        scale so a frame flooded edge-to-edge still reads as all-lit (which marks
        every border clipped) rather than washing out to no contrast."""
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

    def _clipped_sides(self, mask: np.ndarray) -> dict:
        """Which camera borders the projection still spills over. A border is
        clipped when its outer slab is lit beyond ``edge_fraction``."""
        h, w = mask.shape[:2]
        m = max(2, min(h, w) // 200)
        f = self._edge_fraction
        return {
            "left": float(mask[:, :m].mean()) > f,
            "right": float(mask[:, -m:].mean()) > f,
            "top": float(mask[:m, :].mean()) > f,
            "bottom": float(mask[-m:, :].mean()) > f,
        }

    def _sanitize_box(self, x0, y0, x1, y1) -> list[float]:
        """Clamp edges to the projector and keep at least a minimum box size so
        the search can never invert or collapse the box."""
        x0 = min(max(x0, 0.0), self.width - self._min_box_px)
        y0 = min(max(y0, 0.0), self.height - self._min_box_px)
        x1 = max(min(x1, float(self.width)), x0 + self._min_box_px)
        y1 = max(min(y1, float(self.height)), y0 + self._min_box_px)
        return [x0, y0, x1, y1]

    def _write_report(self, x: int, y: int, w: int, h: int) -> None:
        area_frac = (w * h) / float(self.width * self.height) if self.width and self.height else 0.0
        lines = [
            "Camera field-of-view identification",
            f"projector resolution: {self.width} x {self.height}",
            f"iterations: {self._iterations}",
            "",
            "Camera FOV in projector pixels:",
            f"  offset: ({x}, {y})",
            f"  size:   {w} x {h}",
            f"  covers: {100.0 * area_frac:.1f}% of the projector area",
            "",
            "Files: fov_outline.png (projector-space FOV outline), "
            "fov_solid.png (filled), frame_NN.png (per-iteration captures).",
        ]
        path = os.path.join(self._output_dir, "fov.txt")
        with open(path, "w", encoding="ascii") as handle:
            handle.write("\n".join(lines) + "\n")
