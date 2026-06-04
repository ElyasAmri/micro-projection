"""Byte-exact regression guardrail for stl_loader._rasterize_triangles.

Stage 6 B.3b-perf.0. The committed fixture
``tests/fixtures/rasterizer/rasterizer_baseline.npz`` freezes the CURRENT
output of ``_rasterize_triangles`` (reached through the production
``load_stl_heightmap`` path) for the four synthetic meshes the existing
``test_stl_loader`` cases already build. The tests below LOAD that frozen file
and assert ``np.array_equal`` (EXACT — not allclose) against a freshly
rasterized heightmap from the same mesh + shape + pixel size.

Why this exists
---------------
The existing ``test_stl_loader`` cases assert with ``atol`` 0.1-0.25 plus two
trivial exact-array checks (all-zeros walls; translation invariance) — none of
which pin a non-trivial pixel value. They would NOT catch a byte-level drift in
the per-pixel upper-envelope. This fixture is the byte-identical guardrail for
the perf.1 vectorization of ``_rasterize_triangles``: the committed array is the
frozen "current output"; the vectorized code must reproduce it bit-for-bit.

The fixture is generated ONCE, out of band, by
``scripts/build_rasterizer_fixtures.py`` and committed. It is NEVER regenerated
at test time — a self-regenerating fixture would tautologically match itself and
prove nothing. ``SPECS`` and ``_rasterize_via_loader`` below are the single
source of truth shared with that generator (it imports them from here), so the
frozen array and the fresh comparison array are produced by identical generation
logic and the ONLY thing that can differ is the rasterizer code under guard.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from test_stl_loader import (
    _box,
    _pyramid,
    _tilted_triangle,
    _uv_sphere,
    _write_stl,
)
from stl_loader import load_stl_heightmap

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "rasterizer" / "rasterizer_baseline.npz"
)

# Single source of truth for mesh + params, shared with the generator script.
# Shapes / pixel sizes match the existing test_stl_loader cases (small enough to
# commit). The meshes are the existing helpers — no new geometry is invented.
SPECS = [
    {"key": "cube", "build": lambda: _box(0, 0, 0, 10, 10, 10),
     "shape": (200, 240), "pixel_size_mm": 0.1},
    {"key": "pyramid", "build": lambda: _pyramid(5.0, 6.0),
     "shape": (220, 220), "pixel_size_mm": 0.1},
    {"key": "sphere", "build": lambda: _uv_sphere(4.0, 72, 72),
     "shape": (240, 240), "pixel_size_mm": 0.1},
    {"key": "tilted", "build": lambda: _tilted_triangle(),
     "shape": (160, 160), "pixel_size_mm": 0.1},
]
SPECS_BY_KEY = {s["key"]: s for s in SPECS}


def _rasterize_via_loader(spec: dict, out_dir) -> np.ndarray:
    """Rasterize a spec's mesh through the production ``load_stl_heightmap`` path.

    Writes the mesh to a binary STL in ``out_dir`` then loads it — exactly the
    path the existing ``test_stl_loader`` cases use, including numpy-stl's
    float32 round-trip. Both the generator and the comparison test call this, so
    the frozen and fresh arrays share identical generation logic; the only
    variable left is ``_rasterize_triangles`` itself.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tris = spec["build"]()
    path = _write_stl(tris, out_dir / f"{spec['key']}.stl")
    return load_stl_heightmap(path, spec["shape"], spec["pixel_size_mm"])


def _load_frozen() -> dict:
    if not FIXTURE_PATH.exists():
        pytest.fail(
            f"Rasterizer fixture missing: {FIXTURE_PATH}\n"
            f"Generate it (once) via:\n"
            f"    python scripts/build_rasterizer_fixtures.py"
        )
    with np.load(FIXTURE_PATH) as data:
        return {k: data[k].copy() for k in data.files}


@pytest.fixture(scope="module")
def frozen_rasterizer_baseline() -> dict:
    """The committed frozen arrays, loaded from disk (never regenerated here)."""
    return _load_frozen()


@pytest.mark.parametrize("key", [s["key"] for s in SPECS])
def test_rasterizer_output_matches_frozen_fixture(
    key, frozen_rasterizer_baseline, tmp_path,
):
    """Current ``_rasterize_triangles`` output equals the committed frozen array
    bit-for-bit. This is the byte-identical guardrail for the perf.1
    vectorization — exact equality, NOT a tolerance check."""
    assert key in frozen_rasterizer_baseline, (
        f"frozen fixture has no array for {key!r}; regenerate via "
        f"scripts/build_rasterizer_fixtures.py"
    )
    frozen = frozen_rasterizer_baseline[key]
    fresh = _rasterize_via_loader(SPECS_BY_KEY[key], tmp_path)

    assert fresh.shape == frozen.shape, (key, fresh.shape, frozen.shape)
    assert fresh.dtype == frozen.dtype == np.float64
    assert np.array_equal(fresh, frozen), (
        f"{key}: fresh rasterize diverged from frozen fixture "
        f"(max abs diff {np.abs(fresh - frozen).max():.3e})"
    )


@pytest.mark.parametrize("key", [s["key"] for s in SPECS])
def test_rasterizer_is_deterministic_within_run(key, tmp_path):
    """Two rasterizations of the same mesh in one run are bit-identical. If this
    fails the rasterizer is non-deterministic and the frozen-fixture guardrail
    itself is unsound — that is a finding, not a flake."""
    a = _rasterize_via_loader(SPECS_BY_KEY[key], tmp_path / "a")
    b = _rasterize_via_loader(SPECS_BY_KEY[key], tmp_path / "b")
    assert np.array_equal(a, b)
