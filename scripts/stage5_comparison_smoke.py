"""Stage 5 sub-task 4 smoke — recovered vs ground-truth comparison view.

One-shot, non-interactive. Renders RecoveredComparisonView with two
deliberately divergent surfaces and captures the framebuffer so the
translucent-over-solid overlap can be eyeballed.

Run ONE mode per process invocation (one-process-per-render rule):

    python scripts/stage5_comparison_smoke.py both    # recovered + ground truth
    python scripts/stage5_comparison_smoke.py recovered  # GT toggled off
    python scripts/stage5_comparison_smoke.py ground_truth  # recovered toggled off

`both` is the headline (must read as two distinguishable surfaces).
`recovered` / `ground_truth` exercise the toggle paths visually;
`ground_truth` alone verifies the translucent surface renders with nothing
opaque behind it (a real depth-sort edge case).
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
from PyQt6.QtWidgets import QApplication

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

from src.gui.comparison_view import RecoveredComparisonView  # noqa: E402

SHAPE = (550, 680)
PS = 0.1


def _pump(app: QApplication, ms: int = 1500, step_ms: int = 50) -> None:
    from PyQt6.QtCore import QElapsedTimer

    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        app.processEvents()
        QApplication.instance().thread().msleep(step_ms)


def _divergent_surfaces():
    """recovered = Gaussian bump; ground_truth = same bump + a localized
    +4 mm offset in a central square, so the two surfaces visibly diverge
    (amber GT pokes above blue recovered in the center, coincide outside)."""
    H, W = SHAPE
    x = (np.arange(W) - (W - 1) / 2.0) * PS
    y = (np.arange(H) - (H - 1) / 2.0) * PS
    xx, yy = np.meshgrid(x, y)
    recovered = 8.0 * np.exp(-(xx ** 2 + yy ** 2) / (2.0 * 12.0 ** 2))
    inner = (np.abs(xx) <= 12.0) & (np.abs(yy) <= 12.0)
    ground_truth = recovered + np.where(inner, 4.0, 0.0)
    return recovered, ground_truth


def run(mode: str) -> int:
    app = QApplication(sys.argv)
    view = RecoveredComparisonView(shape=SHAPE, pixel_size_mm=PS)
    view.resize(900, 700)
    view.show()

    recovered, ground_truth = _divergent_surfaces()
    view.set_data(recovered, ground_truth)

    if mode == "recovered":
        view.set_ground_truth_visible(False)
    elif mode == "ground_truth":
        view.set_recovered_visible(False)

    _pump(app)

    out = os.path.join(tempfile.gettempdir(), f"stage5_comparison_{mode}.png")
    view.grabFramebuffer().save(out)
    print(f"[{mode}] screenshot={out}")
    return 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) == 2 else "both"
    if mode not in ("both", "recovered", "ground_truth"):
        print("usage: python scripts/stage5_comparison_smoke.py "
              "{both|recovered|ground_truth}")
        return 2
    return run(mode)


if __name__ == "__main__":
    raise SystemExit(main())
