"""scripts/build_regression_fixtures.py — Generate tests/regression_data.npz.

Executes the current Fringe_Projection_Python.ipynb end-to-end in a fresh
Python namespace and saves the six reference arrays consumed by Stage 2
regression tests:

    phi1            — analytical biased phase on flat reference (cell 3)
    phi1_unwrapped  — recovered unwrapped phase on flat (cell 7)
    phi2            — calibration / inverse-grating correction phase (cell 11)
    phi3_unwrapped  — recovered unwrapped phase on the object (cell 17)
    H_rec0          — DC-aligned recovered height (cell 20)
    H_obj           — synthetic Gaussian ground truth (cell 13)

Output is written via `np.savez_compressed`; pickle is intentionally avoided
so the fixture is portable across Python and NumPy versions.

Re-run this script whenever the notebook changes in a way that affects the
fixture arrays.

Usage from the project root:
    python scripts/build_regression_fixtures.py
"""
from __future__ import annotations

import os

# matplotlib backend MUST be set before any module imports it.
os.environ.setdefault("MPLBACKEND", "Agg")

import contextlib
import io
import sys
import warnings
from pathlib import Path

import numpy as np
import nbformat

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK = ROOT / "Fringe_Projection_Python.ipynb"
OUTPUT = ROOT / "tests" / "regression_data.npz"

WANTED = ["phi1", "phi1_unwrapped", "phi2", "phi3_unwrapped", "H_rec0", "H_obj"]


def main() -> int:
    if not NOTEBOOK.exists():
        print(f"Notebook not found: {NOTEBOOK}", file=sys.stderr)
        return 1

    nb = nbformat.read(NOTEBOOK, as_version=4)

    sources: list[str] = []
    for i, cell in enumerate(nb.cells):
        if cell.cell_type != "code":
            continue
        src = cell.source
        # Defensively strip notebook magics or shell-out lines if any creep in.
        cleaned_lines = []
        for line in src.splitlines():
            stripped = line.lstrip()
            if stripped.startswith(("%", "!")):
                continue
            cleaned_lines.append(line)
        sources.append(f"# --- cell {i} ---\n" + "\n".join(cleaned_lines))

    code = "\n\n".join(sources)

    ns: dict = {"__name__": "__main__"}
    with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        exec(compile(code, str(NOTEBOOK), "exec"), ns)

    missing = [k for k in WANTED if k not in ns]
    if missing:
        print(
            f"Notebook did not define expected variables: {missing}",
            file=sys.stderr,
        )
        return 2

    arrays = {k: np.asarray(ns[k]) for k in WANTED}

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUTPUT, **arrays)

    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    print("Variables saved:")
    for k, v in arrays.items():
        print(
            f"  {k:>16}: shape={v.shape}, dtype={v.dtype}, "
            f"min={float(v.min()):.4e}, max={float(v.max()):.4e}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
