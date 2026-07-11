"""Camera field-of-view identification (ported from the original hardware app).

Finds the projector pixel region the camera sees -- the camera FOV expressed
in projector coordinates. The projector draws a filled bright box; each
captured frame is thresholded to a bright mask, and each of the four box
edges runs an independent search against its camera border: while the
projection still spills over that border the edge moves inward, once it no
longer does the edge moves outward.

Each edge keeps its full-size step until its clip state first flips (it has
bracketed the FOV boundary) and only then starts halving to refine. Halving
before bracketing would cap an edge's travel at ~2x the initial step and
strand edges whose boundary is far away -- the bug that originally left the
side edges short of the FOV.

Frames that read as dark (nothing projected yet) are skipped: they neither
move an edge nor decay a step.

Assumes the projector and camera axes are roughly aligned (no large rotation,
camera ReverseX/ReverseY off): camera-left clipping maps to the box's left
edge, and so on. A mirrored or strongly rotated mounting needs an
axis-mapping step first.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6.QtCore import QThread, Signal


def solid_box(width: int, height: int, box, level: int = 255) -> np.ndarray:
    """Filled bright rectangle at box = (x0, y0, x1, y1) in projector pixels."""
    img = np.zeros((height, width), dtype=np.uint8)
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, x1), min(height, y1)
    if x1 > x0 and y1 > y0:
        img[y0:y1, x0:x1] = int(np.clip(level, 0, 255))
    return img


def box_outline(width: int, height: int, box, level: int = 255,
                thickness: int = 4) -> np.ndarray:
    """Hollow rectangle outline at box, so the operator can see the matched
    FOV on the projector without flooding the scene with light."""
    img = np.zeros((height, width), dtype=np.uint8)
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, x1), min(height, y1)
    if x1 <= x0 or y1 <= y0:
        return img
    t = max(1, int(thickness))
    val = int(np.clip(level, 0, 255))
    img[y0:y1, x0:min(x0 + t, x1)] = val
    img[y0:y1, max(x1 - t, x0):x1] = val
    img[y0:min(y0 + t, y1), x0:x1] = val
    img[max(y1 - t, y0):y1, x0:x1] = val
    return img


@dataclass
class FovParams:
    """Search tuning; resolution-relative, so the defaults travel."""
    iterations: int = 32
    level: int = 255
    # A camera pixel counts as lit at this fraction of full scale.
    bright_fraction: float = 0.4
    # A camera border counts as still-clipped when this fraction of its outer
    # slab is lit.
    edge_fraction: float = 0.05
    # Below this lit fraction the frame is treated as un-projected (settling)
    # and skipped.
    dark_fraction: float = 0.005
    min_box_px: int = 16


class FovSearch:
    """The pure search: feed camera frames, read back the projector-space box.
    No Qt, no I/O -- drives cleanly from a worker or a test."""

    # Box edges and the camera border each maps to (box index, inward sign):
    # moving an edge "inward" shrinks the box.
    _EDGES = (("left", 0, +1), ("right", 2, -1), ("top", 1, +1), ("bottom", 3, -1))

    def __init__(self, proj_w: int, proj_h: int,
                 params: FovParams | None = None) -> None:
        self.w, self.h = int(proj_w), int(proj_h)
        self.p = params or FovParams()
        self.box = [0.0, 0.0, float(self.w), float(self.h)]  # x0, y0, x1, y1
        step0 = max(2.0, min(self.w, self.h) / 4.0)
        self._step = {name: step0 for name, _, _ in self._EDGES}
        self._prev = {name: None for name, _, _ in self._EDGES}

    def pattern(self) -> np.ndarray:
        return solid_box(self.w, self.h, self.box, level=self.p.level)

    def update(self, image: np.ndarray) -> bool:
        """Fold one captured frame into the search. Returns False for a dark
        (skipped) frame, True when an update was applied."""
        mask = self._bright_mask(np.asarray(image))
        if float(mask.mean()) < self.p.dark_fraction:
            return False
        clipped = self._clipped_sides(mask)
        box = list(self.box)
        for name, idx, inward in self._EDGES:
            c = clipped[name]
            prev = self._prev[name]
            # Halve only once this edge has bracketed the boundary (clip state
            # flipped); until then keep the full step so it can travel however
            # far the FOV boundary is.
            if prev is not None and prev != c:
                self._step[name] = max(1.0, self._step[name] / 2.0)
            self._prev[name] = c
            step = self._step[name]
            box[idx] += inward * step if c else -inward * step
        self.box = self._sanitize(*box)
        return True

    def result(self) -> tuple[int, int, int, int]:
        """(x, y, w, h) of the converged box, in projector pixels."""
        x0, y0, x1, y1 = (int(round(v)) for v in self.box)
        return x0, y0, x1 - x0, y1 - y0

    def _bright_mask(self, image: np.ndarray) -> np.ndarray:
        """Lit camera pixels at a fraction of *full scale* (not the frame max),
        so a frame flooded edge-to-edge reads as all-lit -- every border
        clipped -- rather than washing out to no contrast."""
        img = image
        if img.ndim == 3:
            img = img.mean(axis=2)
        if img.dtype == np.uint16:
            maxval = 65535.0
        elif img.dtype == np.uint8:
            maxval = 255.0
        else:
            maxval = float(img.max()) or 1.0
        return img.astype(np.float64) / maxval >= self.p.bright_fraction

    def _clipped_sides(self, mask: np.ndarray) -> dict:
        h, w = mask.shape[:2]
        m = max(2, min(h, w) // 200)
        f = self.p.edge_fraction
        return {
            "left": float(mask[:, :m].mean()) > f,
            "right": float(mask[:, -m:].mean()) > f,
            "top": float(mask[:m, :].mean()) > f,
            "bottom": float(mask[-m:, :].mean()) > f,
        }

    def _sanitize(self, x0, y0, x1, y1) -> list[float]:
        """Clamp to the projector and keep a minimum size so the search can
        never invert or collapse the box."""
        x0 = min(max(x0, 0.0), self.w - self.p.min_box_px)
        y0 = min(max(y0, 0.0), self.h - self.p.min_box_px)
        x1 = max(min(x1, float(self.w)), x0 + self.p.min_box_px)
        y1 = max(min(y1, float(self.h)), y0 + self.p.min_box_px)
        return [x0, y0, x1, y1]


def write_outputs(out_dir: Path, search: FovSearch) -> Path:
    """fov_outline.png / fov_solid.png (projector space) and fov.txt."""
    import cv2

    out_dir.mkdir(parents=True, exist_ok=True)
    x, y, w, h = search.result()
    cv2.imwrite(str(out_dir / "fov_outline.png"),
                box_outline(search.w, search.h, search.box))
    cv2.imwrite(str(out_dir / "fov_solid.png"), search.pattern())
    area = (w * h) / float(search.w * search.h) if search.w and search.h else 0.0
    report = out_dir / "fov.txt"
    report.write_text("\n".join([
        "Camera field-of-view identification",
        f"projector resolution: {search.w} x {search.h}",
        "",
        "Camera FOV in projector pixels:",
        f"  offset: ({x}, {y})",
        f"  size:   {w} x {h}",
        f"  covers: {100.0 * area:.1f}% of the projector area",
    ]) + "\n", encoding="utf-8")
    return report


class FovWorker(QThread):
    """Iterate the search against the live rig: show the box, settle, grab,
    update; finish by projecting the matched outline and writing the report."""

    line = Signal(str)
    failed = Signal(str)
    finished_ok = Signal(tuple)  # (x, y, w, h) in projector pixels
    show_pattern = Signal(object)  # -> projector.show_pattern (blocking, GUI thread)

    def __init__(self, search: FovSearch, camera_service, out_dir: Path, *,
                 settle_ms: int = 200, save_frames: bool = True,
                 parent=None) -> None:
        super().__init__(parent)
        self._search = search
        self._service = camera_service
        self._out_dir = out_dir
        self._settle_ms = settle_ms
        self._save_frames = save_frames

    def run(self) -> None:
        import cv2

        s = self._search
        try:
            self._service.acquire_step(s.p.iterations)
        except Exception as exc:  # noqa: BLE001 - camera never became available
            self.failed.emit(f"camera unavailable: {exc}")
            return
        try:
            self._out_dir.mkdir(parents=True, exist_ok=True)
            for k in range(s.p.iterations):
                if self.isInterruptionRequested():
                    raise RuntimeError("aborted (app closing)")
                self.show_pattern.emit(s.pattern())  # blocks until on screen
                self.msleep(self._settle_ms)
                frame = self._service.grab_step()
                if self._save_frames:
                    cv2.imwrite(str(self._out_dir / f"frame_{k:02d}.png"), frame)
                if not s.update(frame):
                    self.line.emit(f"[fov] frame {k + 1} dark, skipped")
                    continue
                x, y, w, h = s.result()
                self.line.emit(f"[fov] iter {k + 1}/{s.p.iterations}: "
                               f"{w} x {h} at ({x}, {y})")
            # Show the operator the camera's own FOV, without flooding the
            # scene with light.
            self.show_pattern.emit(box_outline(s.w, s.h, s.box))
        except Exception as exc:  # noqa: BLE001 - surface any capture failure
            self.failed.emit(f"FOV identification failed: {exc}")
            return
        finally:
            self._service.release_step()
        report = write_outputs(self._out_dir, s)
        self.line.emit(f"[fov] report: {report}")
        self.finished_ok.emit(s.result())
