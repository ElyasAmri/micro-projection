"""coordinate_grid.py — labeled XYZ mm measurement grid for the GL views.

Stage 5 sub-task 3. A standalone, reusable component that produces the GL
items for a measurement grid with mm-labeled ticks, for the future
"Recovered Surface" comparison tab.

pyqtgraph 0.14.0 has GLGridItem, GLAxisItem, and GLTextItem but NO
built-in ticked/labeled axis (recon Q2), so the tick labels are placed by
hand. The design follows the math-layer-purity discipline (cf.
clip_detection.py): the tick math is a PURE function, headlessly testable
with no Qt/GL; the GL-item assembly is a thin class on top.

Coordinate convention
---------------------
Matches surface_preview.py / test_surfaces.py:
- X horizontal (mm), Y vertical (mm), Z height (mm).
- Centered grid: a (H, W) surface at `pixel_size_mm` spans
      x in [-(W-1)/2 * ps, +(W-1)/2 * ps]
      y in [-(H-1)/2 * ps, +(H-1)/2 * ps]
  (the same extent the surface vertices occupy — see
  SurfacePreview._rebuild_coordinate_arrays), so the grid aligns with the
  rendered surface. X/Y are fixed by the FOV; Z is data-dependent and
  passed in.
- Honest scale: Z is NOT exaggerated (Z_EXAGGERATION = 1.0 doctrine).
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np
import pyqtgraph.opengl as gl
from PyQt6.QtGui import QFont


# --- Visual style -----------------------------------------------------------
# Axis line colors (RGBA floats 0..1) — chosen to read against the (30,30,30)
# dark background and over the recovered/ground-truth surfaces.
_X_AXIS_COLOR = (1.0, 0.45, 0.45, 1.0)   # warm red
_Y_AXIS_COLOR = (0.45, 1.0, 0.55, 1.0)   # green
_Z_AXIS_COLOR = (0.50, 0.70, 1.0, 1.0)   # blue
_AXIS_WIDTH = 2.0

# Grid plane lines: subtle gray (RGBA ints 0..255 via setColor).
_GRID_COLOR = (255, 255, 255, 40)

# Label legibility (ADD-TO-SCOPE): GLTextItem defaults to glOptions
# 'additive', which over a bright surface oversaturates and over varied
# color washes out unpredictably. Use 'translucent' with an opaque near-
# white color so the mm numbers read deterministically against both the
# dark background and the surfaces. Verified by the grid smoke screenshot.
_LABEL_COLOR = (235, 235, 235, 255)
_LABEL_GLOPTIONS = "translucent"
_LABEL_FONT = QFont("Helvetica", 12)

# Margin (mm) placing tick labels just outside the grid edge so they don't
# sit under the surface.
_LABEL_MARGIN_MM = 3.0

# Tick density. X/Y are physically large (FOV-sized, ~55-68 mm) and take a
# normal count. Z is physically short and data-dependent (often a few mm of
# relief at honest 1x scale); GLTextItem labels are fixed pixel size, so a
# short Z axis with many ticks stacks into an unreadable pile (verified in
# the grid smoke screenshot). Z therefore uses a lower default count. Both
# stay parameterized.
DEFAULT_XY_TARGET_TICKS = 7
DEFAULT_Z_TARGET_TICKS = 4

# Below this Z span (mm), even 3-4 nice-step ticks stack/occlude on the
# short axis. Collapse to endpoints + zero only (2-3 labels that cannot
# pile up). Above it, normal nice-step ticks. (Lever 1 of the short-Z
# legibility fix.)
_Z_SMALL_SPAN_MM = 15.0

# Lateral offset (mm, in -X) pushing Z tick labels off the Z axis line so
# they don't collide with the line or sit under the surface plane. (Lever 2.)
_Z_LABEL_OFFSET_MM = 4.0


# ---------------------------------------------------------------------------
# PURE tick-computation core (no Qt / GL — headlessly testable).
# ---------------------------------------------------------------------------
def _nice_step(raw_step: float) -> float:
    """Round `raw_step` UP to the nearest 1/2/5 x 10^k 'nice' value.

    Classic axis-tick step selection. Returns a positive step; a
    non-positive raw step falls back to 1.0.
    """
    if not math.isfinite(raw_step) or raw_step <= 0.0:
        return 1.0
    exp = math.floor(math.log10(raw_step))
    base = 10.0 ** exp
    frac = raw_step / base  # in [1, 10)
    if frac <= 1.0:
        nice = 1.0
    elif frac <= 2.0:
        nice = 2.0
    elif frac <= 5.0:
        nice = 5.0
    else:
        nice = 10.0
    return nice * base


def _format_label(value: float, step: float) -> str:
    """Format a tick value as a label string.

    Integer labels when the step is >= 1 mm (steps are always 1/2/5 x 10^k,
    so step >= 1 => integer ticks); otherwise enough decimals to resolve the
    step. Negative zero is normalized to "0".
    """
    if abs(value) < step * 1e-6:
        value = 0.0  # squash float residue / negative zero
    if step >= 1.0:
        return f"{value:.0f}"
    decimals = max(0, int(math.ceil(-math.log10(step))))
    return f"{value:.{decimals}f}"


def compute_axis_ticks(
    min_mm: float,
    max_mm: float,
    target_ticks: int = 7,
) -> List[Tuple[float, str]]:
    """Nice-step tick positions (mm) + label strings for one axis.

    Parameters
    ----------
    min_mm, max_mm : float
        Axis extent in mm. Order-insensitive (swapped if reversed).
    target_ticks : int
        Approximate desired number of ticks; the nice-step rounding means
        the actual count is near, not exactly, this. Parameterized so the
        data-dependent Z axis can request a different density than X/Y.

    Returns
    -------
    list of (position_mm, label_str), sorted ascending. Always includes 0
    when 0 lies within the extent. A degenerate extent (min == max, or a
    non-finite/empty span) returns a single tick at `min_mm`.
    """
    if min_mm > max_mm:
        min_mm, max_mm = max_mm, min_mm
    span = max_mm - min_mm
    if not math.isfinite(span) or span <= 0.0:
        # Degenerate (e.g. Flat mode, or startup before a surface loads):
        # one tick, no division by the zero span anywhere.
        return [(float(min_mm), _format_label(float(min_mm), 1.0))]

    step = _nice_step(span / max(int(target_ticks), 1))
    # First tick at or above min_mm; last at or below max_mm.
    start = math.ceil(min_mm / step - 1e-9) * step
    ticks: List[Tuple[float, str]] = []
    v = start
    while v <= max_mm + 1e-9:
        pos = 0.0 if abs(v) < step * 1e-6 else float(v)
        ticks.append((pos, _format_label(pos, step)))
        v += step
    if not ticks:  # safety: extent narrower than one step
        ticks = [(float(min_mm), _format_label(float(min_mm), step))]
    return ticks


def compute_z_ticks(
    z_min_mm: float,
    z_max_mm: float,
    target_ticks: int = DEFAULT_Z_TARGET_TICKS,
    small_span_mm: float = _Z_SMALL_SPAN_MM,
) -> List[Tuple[float, str]]:
    """Tick positions + labels for the (short, data-dependent) Z axis.

    Z relief at honest 1x scale is usually only a few mm, and GLTextItem
    labels are fixed pixel size, so nice-step ticks crowd and occlude on a
    short axis. For a small span (< `small_span_mm`) collapse to endpoints +
    zero — at most three labels that physically cannot stack:
        - the two endpoints (z_min, z_max), and
        - 0 if it lies strictly between them.
    For a large span, defer to the normal nice-step `compute_axis_ticks`.

    A degenerate span (z_min == z_max, e.g. Flat mode) returns a single
    tick, same as `compute_axis_ticks`.
    """
    if z_min_mm > z_max_mm:
        z_min_mm, z_max_mm = z_max_mm, z_min_mm
    span = z_max_mm - z_min_mm
    if not math.isfinite(span) or span <= 0.0:
        return [(float(z_min_mm), _format_label(float(z_min_mm), 1.0))]
    if span >= small_span_mm:
        return compute_axis_ticks(z_min_mm, z_max_mm, target_ticks)

    # Small span: endpoints + (zero if strictly inside). Use a span-derived
    # step only for label decimal precision.
    step = _nice_step(span / 2.0)
    ticks: List[Tuple[float, str]] = [
        (float(z_min_mm), _format_label(float(z_min_mm), step)),
        (float(z_max_mm), _format_label(float(z_max_mm), step)),
    ]
    if z_min_mm < 0.0 < z_max_mm:
        ticks.insert(1, (0.0, _format_label(0.0, step)))
    return ticks


def _axis_step(min_mm: float, max_mm: float, target_ticks: int = 7) -> float:
    """The nice step the grid-line spacing should use for an axis."""
    span = abs(max_mm - min_mm)
    if not math.isfinite(span) or span <= 0.0:
        return 1.0
    return _nice_step(span / max(int(target_ticks), 1))


# ---------------------------------------------------------------------------
# Thin GL-assembly layer (consumes the pure tick logic above).
# ---------------------------------------------------------------------------
class CoordinateGrid:
    """Holds the GL items for a labeled XYZ mm measurement grid.

    X/Y extents are fixed by the surface FOV (derived from shape x
    pixel_size); Z is data-dependent and (re)built via `set_z_extent`. Add
    every item to a GLViewWidget with `add_to(view)`.
    """

    def __init__(
        self,
        shape: Tuple[int, int],
        pixel_size_mm: float,
        z_min_mm: float = 0.0,
        z_max_mm: float = 0.0,
        target_ticks: int = DEFAULT_XY_TARGET_TICKS,
        z_target_ticks: int = DEFAULT_Z_TARGET_TICKS,
    ) -> None:
        H, W = shape
        # Match SurfacePreview._rebuild_coordinate_arrays centering exactly
        # so the grid aligns with the surface vertices (don't hardcode
        # +-34 / +-27.5 — derive from shape x pixel_size).
        self._x_max = (W - 1) / 2.0 * pixel_size_mm
        self._y_max = (H - 1) / 2.0 * pixel_size_mm
        self._target_ticks = int(target_ticks)
        self._z_target_ticks = int(z_target_ticks)
        self._view: Optional[gl.GLViewWidget] = None

        self._grid_item = self._build_grid()
        self._x_axis_item = self._build_axis_line(
            (-self._x_max, 0.0, 0.0), (self._x_max, 0.0, 0.0), _X_AXIS_COLOR
        )
        self._y_axis_item = self._build_axis_line(
            (0.0, -self._y_max, 0.0), (0.0, self._y_max, 0.0), _Y_AXIS_COLOR
        )
        self._xy_label_items = self._build_xy_labels()

        # Z-dependent items (rebuilt on set_z_extent).
        self._z_axis_item: Optional[gl.GLLinePlotItem] = None
        self._z_label_items: List[gl.GLTextItem] = []
        self._build_z_items(z_min_mm, z_max_mm)

    # -- construction helpers ------------------------------------------------
    def _build_grid(self) -> gl.GLGridItem:
        grid = gl.GLGridItem()
        grid.setSize(x=2.0 * self._x_max, y=2.0 * self._y_max)
        grid.setSpacing(
            x=_axis_step(-self._x_max, self._x_max, self._target_ticks),
            y=_axis_step(-self._y_max, self._y_max, self._target_ticks),
        )
        grid.setColor(_GRID_COLOR)
        return grid

    @staticmethod
    def _build_axis_line(p0, p1, color) -> gl.GLLinePlotItem:
        pos = np.array([p0, p1], dtype=np.float32)
        return gl.GLLinePlotItem(
            pos=pos, color=color, width=_AXIS_WIDTH, antialias=True
        )

    @staticmethod
    def _make_label(pos, text: str) -> gl.GLTextItem:
        return gl.GLTextItem(
            pos=np.array(pos, dtype=np.float32),
            text=text,
            color=_LABEL_COLOR,
            font=_LABEL_FONT,
            glOptions=_LABEL_GLOPTIONS,
        )

    def _build_xy_labels(self) -> List[gl.GLTextItem]:
        labels: List[gl.GLTextItem] = []
        # X tick labels along the front edge (y = -y_max - margin).
        for x, txt in compute_axis_ticks(
            -self._x_max, self._x_max, self._target_ticks
        ):
            labels.append(
                self._make_label(
                    (x, -self._y_max - _LABEL_MARGIN_MM, 0.0), txt
                )
            )
        # Y tick labels along the left edge (x = -x_max - margin).
        for y, txt in compute_axis_ticks(
            -self._y_max, self._y_max, self._target_ticks
        ):
            labels.append(
                self._make_label(
                    (-self._x_max - _LABEL_MARGIN_MM, y, 0.0), txt
                )
            )
        return labels

    def _build_z_items(self, z_min_mm: float, z_max_mm: float) -> None:
        """(Re)build the Z axis line + Z tick labels for the given range.

        Flat/zero range (z_min == z_max, e.g. Flat mode or startup): the
        axis line degenerates to a zero-length segment (harmless, invisible)
        and `compute_axis_ticks` returns a single "0" tick. No span division
        occurs, so there is no divide-by-zero.
        """
        # Z axis runs up the back-left corner so it doesn't pierce the
        # surface in the middle of the view.
        cx = -self._x_max - _LABEL_MARGIN_MM
        cy = -self._y_max - _LABEL_MARGIN_MM
        self._z_axis_item = self._build_axis_line(
            (cx, cy, z_min_mm), (cx, cy, z_max_mm), _Z_AXIS_COLOR
        )
        # Labels: collapse-on-small-span ticks (lever 1), pushed laterally
        # off the axis line in -X so they clear the line and the surface
        # plane (lever 2).
        self._z_label_items = [
            self._make_label((cx - _Z_LABEL_OFFSET_MM, cy, z), txt)
            for z, txt in compute_z_ticks(
                z_min_mm, z_max_mm, self._z_target_ticks
            )
        ]

    # -- public API ----------------------------------------------------------
    def items(self) -> List[object]:
        """All GL items, in add order."""
        out: List[object] = [
            self._grid_item,
            self._x_axis_item,
            self._y_axis_item,
            *self._xy_label_items,
        ]
        if self._z_axis_item is not None:
            out.append(self._z_axis_item)
        out.extend(self._z_label_items)
        return out

    @property
    def label_items(self) -> List[gl.GLTextItem]:
        """Every tick label (X + Y + Z) — used by tests/inspection."""
        return [*self._xy_label_items, *self._z_label_items]

    def add_to(self, view: gl.GLViewWidget) -> None:
        """Add every grid item to `view`. Remembers the view so a later
        `set_z_extent` can swap the Z items in place."""
        self._view = view
        for item in self.items():
            view.addItem(item)

    def set_z_extent(self, z_min_mm: float, z_max_mm: float) -> None:
        """Rebuild the Z axis + labels for a new height range.

        Safe before or after `add_to`. When attached to a view, the old Z
        items are removed and the new ones added so the view stays in sync.
        """
        attached = self._view is not None
        if attached:
            if self._z_axis_item is not None:
                self._view.removeItem(self._z_axis_item)
            for item in self._z_label_items:
                self._view.removeItem(item)
        self._build_z_items(z_min_mm, z_max_mm)
        if attached:
            self._view.addItem(self._z_axis_item)
            for item in self._z_label_items:
                self._view.addItem(item)
