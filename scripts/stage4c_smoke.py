"""Stage 4c sub-task 1 smoke test — dropdown reduction + amplitude cap.

One-shot, non-interactive. Run ONE mode per process invocation:

    python scripts/stage4c_smoke.py verify
    python scripts/stage4c_smoke.py Flat
    python scripts/stage4c_smoke.py Gaussian

`verify`   constructs MainWindow and asserts the surviving dropdown is
           exactly ["Flat", "Gaussian"] and that the Gaussian amplitude
           slider's effective float maximum is 55.0 mm. No capture.

`Flat` / `Gaussian`
           constructs MainWindow, selects that surface, sets the
           surviving sliders to representative non-default values,
           pumps Qt events until the GL view has rendered, then writes
           view_3d.grabFramebuffer() to %TEMP% and prints the absolute
           path.

Each surface MUST run in its own process: Stage 4b established that a
single-process loop leaves all-but-the-first framebuffer blank.
"""
from __future__ import annotations

import os
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# main_window.py mixes `from geometry import ...` (src/ on path) with
# `from src.gui...` (repo root on path); both roots are required.
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from src.gui.main_window import MainWindow  # noqa: E402


def _pump(app: QApplication, ms: int = 2000, step_ms: int = 50) -> None:
    """Process Qt events for ~`ms` so the GL scene actually renders."""
    from PyQt6.QtCore import QElapsedTimer

    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        app.processEvents()
        QApplication.instance().thread().msleep(step_ms)


def _amplitude_float_max(w: MainWindow) -> float:
    s = w.gaussian_amplitude
    # LabeledFloatSlider has no .maximum(); the bound lives on the inner
    # scaled-int QSlider. Effective float max = inner max / scale.
    return s._slider.maximum() / s._scale


def run_verify() -> int:
    app = QApplication(sys.argv)
    w = MainWindow()

    labels = [
        w.surface_combo.itemText(i) for i in range(w.surface_combo.count())
    ]
    amp_max = _amplitude_float_max(w)

    ok_labels = labels == ["Flat", "Gaussian"]
    ok_amp = amp_max == 55.0

    print(f"[verify] dropdown labels       = {labels}")
    print(f"[verify] expected              = ['Flat', 'Gaussian']")
    print(f"[verify] labels OK             = {ok_labels}")
    print(f"[verify] gaussian amp float max = {amp_max}")
    print(f"[verify] amp-max == 55.0 OK     = {ok_amp}")

    app.quit()
    return 0 if (ok_labels and ok_amp) else 1


def run_capture(surface: str) -> int:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(1100, 800)
    w.show()

    w.surface_combo.setCurrentText(surface)

    if surface == "Flat":
        # Flat has no parameters; selecting it (default launch is
        # Gaussian) is itself the non-default state under test.
        pass
    elif surface == "Gaussian":
        # Defaults are amplitude=0.5, sigma=8.0. Drive both to clearly
        # non-default values that stay inside the new caps
        # (amplitude 0..55, sigma 1..30).
        w.gaussian_amplitude.set_value(30.0)
        w.gaussian_sigma.set_value(14.0)
    else:
        print(f"unknown surface: {surface!r}", file=sys.stderr)
        return 2

    _pump(app, ms=2500)

    img = w.view_3d.grabFramebuffer()
    out = os.path.join(
        tempfile.gettempdir(), f"stage4c_smoke_{surface.lower()}.png"
    )
    img.save(out)
    print(f"[capture] surface = {surface}")
    print(f"[capture] saved   = {os.path.abspath(out)}")

    app.quit()
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    mode = sys.argv[1]
    if mode == "verify":
        return run_verify()
    if mode in ("Flat", "Gaussian"):
        return run_capture(mode)
    print(f"unknown mode: {mode!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
