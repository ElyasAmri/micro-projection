"""scripts/build_rasterizer_fixtures.py — Generate the byte-exact rasterizer baseline.

Writes ``tests/fixtures/rasterizer/rasterizer_baseline.npz``: the frozen CURRENT
output of ``stl_loader._rasterize_triangles`` (reached via ``load_stl_heightmap``)
for the four synthetic meshes defined in ``tests/test_stl_loader.py``. This is the
guardrail for the Stage 6 B.3b-perf.1 vectorization of the rasterizer.

The committed ``.npz`` is the frozen "current output";
``tests/test_rasterizer_fixture.py`` LOADS it and asserts future code reproduces
it bit-for-bit. The mesh + shape + pixel-size specs and the rasterize-via-loader
helper are imported from that test module so generation and verification share
one source of truth.

Re-run this ONLY to deliberately re-baseline (e.g. after a reviewed, intentional
rasterizer change) — NEVER as part of the test run. A self-regenerating fixture
would tautologically match itself and prove nothing.

Usage from the project root:
    python scripts/build_rasterizer_fixtures.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT / "src", ROOT / "tests"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from test_rasterizer_fixture import (  # noqa: E402
    FIXTURE_PATH,
    SPECS,
    _rasterize_via_loader,
)


def main() -> int:
    arrays: dict = {}
    with tempfile.TemporaryDirectory() as td:
        for spec in SPECS:
            arrays[spec["key"]] = _rasterize_via_loader(spec, td)

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(FIXTURE_PATH, **arrays)

    print(f"Wrote {FIXTURE_PATH.relative_to(ROOT)}")
    print("Arrays saved:")
    for k, v in arrays.items():
        print(
            f"  {k:>8}: shape={v.shape}, dtype={v.dtype}, nbytes={v.nbytes}, "
            f"min={float(v.min()):.4e}, max={float(v.max()):.4e}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
