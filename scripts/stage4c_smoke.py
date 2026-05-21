"""Stage 4c smoke test — surface dropdown + STL import.

One-shot, non-interactive. Run ONE mode per process invocation:

    python scripts/stage4c_smoke.py verify
    python scripts/stage4c_smoke.py Flat
    python scripts/stage4c_smoke.py Gaussian
    python scripts/stage4c_smoke.py STL

`verify`   constructs MainWindow and asserts the dropdown is exactly
           ["Flat", "Gaussian", "STL file..."] and that the Gaussian
           amplitude slider's effective float maximum is 120.0 mm. No
           capture.

`Flat` / `Gaussian`
           constructs MainWindow, selects that surface, sets the
           surviving sliders to representative non-default values,
           pumps Qt events until the GL view has rendered, then writes
           view_3d.grabFramebuffer() to %TEMP% and prints the absolute
           path.

`STL`      writes a synthetic 30x30x15 mm cube STL to %TEMP%, drives
           it through MainWindow._load_stl_from_path (bypassing the
           QFileDialog), then captures view_3d.grabFramebuffer().

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

    expected_labels = ["Flat", "Gaussian", "STL file..."]
    ok_labels = labels == expected_labels
    ok_amp = amp_max == 120.0

    print(f"[verify] dropdown labels        = {labels}")
    print(f"[verify] expected               = {expected_labels}")
    print(f"[verify] labels OK              = {ok_labels}")
    print(f"[verify] gaussian amp float max = {amp_max}")
    print(f"[verify] amp-max == 120.0 OK    = {ok_amp}")

    app.quit()
    return 0 if (ok_labels and ok_amp) else 1


def _write_cube_stl(side: float, path: str) -> str:
    """Write a closed-solid cube STL of side `side` mm centered at the
    origin to `path`; return `path`."""
    import numpy as np  # local: keep top-of-file imports unchanged
    from stl import mesh as stl_mesh

    hx = hy = hz = side / 2.0

    def corner(ix, iy, iz):
        return (
            (hx if ix else -hx),
            (hy if iy else -hy),
            (hz if iz else -hz),
        )

    p = {(ix, iy, iz): corner(ix, iy, iz)
         for ix in (0, 1) for iy in (0, 1) for iz in (0, 1)}

    def quad(a, b, c, d):
        return [[p[a], p[b], p[c]], [p[a], p[c], p[d]]]

    tris = []
    tris += quad((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))
    tris += quad((0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0))
    tris += quad((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1))
    tris += quad((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0))
    tris += quad((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0))
    tris += quad((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1))

    data = np.zeros(len(tris), dtype=stl_mesh.Mesh.dtype)
    m = stl_mesh.Mesh(data, remove_empty_areas=False)
    m.vectors[:] = np.asarray(tris, dtype=np.float64)
    m.save(path)
    return path


def run_capture(surface: str) -> int:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(1100, 800)
    w.show()

    if surface == "Flat":
        # Flat has no parameters; selecting it (default launch is
        # Gaussian) is itself the non-default state under test.
        w.surface_combo.setCurrentText(surface)
    elif surface == "Gaussian":
        # Defaults are amplitude=0.5, sigma=8.0. Drive both to clearly
        # non-default values that stay inside the current caps
        # (amplitude 0..120, sigma 1..30).
        w.surface_combo.setCurrentText(surface)
        w.gaussian_amplitude.set_value(30.0)
        w.gaussian_sigma.set_value(14.0)
    elif surface == "STL":
        # 30x30x15 mm cube — well inside the 68x55x120 working volume.
        # Drive through _load_stl_from_path to bypass the QFileDialog
        # entirely; the surface_combo flip to "STL file..." happens via
        # the same setCurrentText path the GUI uses (no cache present
        # would normally open the dialog, so we populate the cache
        # first, then flip the dropdown).
        from pathlib import Path
        stl_path = os.path.join(
            tempfile.gettempdir(), "stage4c_smoke_cube.stl"
        )
        _write_cube_stl(30.0, stl_path)  # 30 mm cube, well under 68/55/120
        ok = w._load_stl_from_path(Path(stl_path))
        if not ok:
            print("[capture] _load_stl_from_path returned False",
                  file=sys.stderr)
            return 3
        w.surface_combo.setCurrentText("STL file...")
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
    if mode in ("Flat", "Gaussian", "STL"):
        return run_capture(mode)
    print(f"unknown mode: {mode!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
