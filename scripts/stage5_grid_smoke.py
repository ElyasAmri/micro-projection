"""Stage 5 sub-task 3 smoke — labeled XYZ coordinate grid.

One-shot, non-interactive. Renders a `CoordinateGrid` in a GLViewWidget on
the standard (30,30,30) dark background and captures the framebuffer so the
mm tick labels can be eyeballed for legibility (ADD-TO-SCOPE: a grid with
invisible labels is a non-deliverable).

Run ONE mode per process invocation (Stage 4b one-process-per-render rule):

    python scripts/stage5_grid_smoke.py grid    # grid alone, Z 0..10 mm
    python scripts/stage5_grid_smoke.py surface  # grid + a sample Gaussian
    python scripts/stage5_grid_smoke.py flat     # flat Z range (z_min==z_max)

Each writes view.grabFramebuffer() to %TEMP% and prints the absolute path.
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
import pyqtgraph.opengl as gl
from PyQt6.QtWidgets import QApplication

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

from src.gui.coordinate_grid import CoordinateGrid  # noqa: E402

# Mirror the math-grid constants without importing main_window (avoids the
# gui import chain in a smoke script).
SURFACE_SHAPE = (550, 680)
SURFACE_PIXEL_SIZE_MM = 0.1


def _pump(app: QApplication, ms: int = 1500, step_ms: int = 50) -> None:
    from PyQt6.QtCore import QElapsedTimer

    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        app.processEvents()
        QApplication.instance().thread().msleep(step_ms)


def _sample_gaussian(shape, ps, amp=8.0, sigma=12.0):
    H, W = shape
    x = (np.arange(W) - (W - 1) / 2.0) * ps
    y = (np.arange(H) - (H - 1) / 2.0) * ps
    xx, yy = np.meshgrid(x, y)
    return amp * np.exp(-(xx ** 2 + yy ** 2) / (2.0 * sigma ** 2))


def run(mode: str) -> int:
    app = QApplication(sys.argv)
    view = gl.GLViewWidget()
    view.setBackgroundColor((30, 30, 30))
    view.resize(900, 700)
    view.show()

    if mode == "flat":
        z_min, z_max = 0.0, 0.0
    else:
        z_min, z_max = 0.0, 10.0

    grid = CoordinateGrid(
        shape=SURFACE_SHAPE,
        pixel_size_mm=SURFACE_PIXEL_SIZE_MM,
        z_min_mm=z_min,
        z_max_mm=z_max,
    )
    grid.add_to(view)

    if mode == "surface":
        hm = _sample_gaussian(SURFACE_SHAPE, SURFACE_PIXEL_SIZE_MM)
        x = (np.arange(SURFACE_SHAPE[1]) - (SURFACE_SHAPE[1] - 1) / 2.0) * SURFACE_PIXEL_SIZE_MM
        y = (np.arange(SURFACE_SHAPE[0]) - (SURFACE_SHAPE[0] - 1) / 2.0) * SURFACE_PIXEL_SIZE_MM
        surf = gl.GLSurfacePlotItem(
            x=x, y=y, z=hm.T, shader="shaded", smooth=False, drawEdges=False
        )
        surf.setColor((0.4, 0.5, 0.55, 1.0))
        view.addItem(surf)
        grid.set_z_extent(float(hm.min()), float(hm.max()))

    view.setCameraPosition(distance=130, elevation=28, azimuth=45)
    _pump(app)

    out = os.path.join(tempfile.gettempdir(), f"stage5_grid_{mode}.png")
    view.grabFramebuffer().save(out)
    print(f"[{mode}] labels={len(grid.label_items)}  screenshot={out}")
    return 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) == 2 else "grid"
    if mode not in ("grid", "surface", "flat"):
        print("usage: python scripts/stage5_grid_smoke.py {grid|surface|flat}")
        return 2
    return run(mode)


if __name__ == "__main__":
    raise SystemExit(main())
