"""No-leak guard: object-space µm constants must not enter the math path.

The scale-bridge constants (Stage 6 A.0.1) are LABELING-ONLY. The simulation
core is sealed in pixel-space, and the sampling envelope (A.0.2) is purely
cycles/pixel. This test fails loudly if any of the µm constants ever appears in
a math-path module:

  - synthetic_fringes.py : carrier, project(), synthesize_psi_stack()
  - pipeline.py          : the (2*pi/p)*X carrier + height path
  - sampling.py          : the contrast envelope (cycles/pixel only)

geometry.py is deliberately NOT checked here: it is the DEFINITION home of the
constants (and the labeling-only pixel_pitch_um field default references one),
so the names legitimately appear there. The guard covers the modules that must
stay free of them.
"""
from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

FORBIDDEN = (
    "OBJECT_SPACE_UM_PER_PIXEL",
    "CAMERA_PIXEL_PITCH_UM",
    "CAMERA_MAGNIFICATION",
)

MATH_PATH_MODULES = (
    "synthetic_fringes.py",
    "pipeline.py",
    "sampling.py",
)


def test_scale_bridge_constants_absent_from_math_path():
    for name in MATH_PATH_MODULES:
        text = (SRC / name).read_text(encoding="utf-8")
        for token in FORBIDDEN:
            assert token not in text, (
                f"scale-bridge constant {token!r} leaked into math-path "
                f"module {name!r} — the core must stay pixel-space and the "
                f"sampling envelope cycles/pixel only."
            )
