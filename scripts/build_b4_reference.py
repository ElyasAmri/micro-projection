"""build_b4_reference.py — generate the Stage 6 B.4 B.3a reference artifact.

Run ONCE to (re)produce the committed reference the Stage 7 hardware phase
validates against:
  tests/fixtures/b4_reference/b3a_reference_config.json  — the B.3a ShowcaseConfig
  tests/fixtures/b4_reference/b3a_reference.npz          — the frozen headline
                                                            numbers + recovered array

    python scripts/build_b4_reference.py

Layering: this SCRIPT may read GUI constants (the live B.3a defaults live in
gui.main_window) to BUILD the config — that's allowed for a one-shot generator.
The numbers themselves are derived purely from core via `derive_b3a_headline`
(imported from tests/test_b4_reference.py — one source, so the committed artifact
and the reload-verify test can never disagree). The reload test re-derives via
the SAME function; it is never regenerated at test time.
"""
from __future__ import annotations

import inspect
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "src", ROOT / "tests"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from geometry import HybridGeometry  # noqa: E402
from io_utils import ShowcaseConfig, save_config  # noqa: E402
from test_surfaces import make_steep_dome  # noqa: E402
# Single source of the re-derivation (also used by the reload-verify test):
from test_b4_reference import (  # noqa: E402
    CONFIG_PATH,
    FIXTURE_DIR,
    NPZ_PATH,
    derive_b3a_headline,
)
# Live B.3a defaults — script may touch GUI constants to build the config.
from gui.main_window import (  # noqa: E402
    GEOMETRY_A_PX,
    GEOMETRY_M,
    GEOMETRY_P_PX,
    NOISE_SEED,
    NOISE_SIGMA,
    STEEP_DEFECT_AMP_PX,
    STEEP_DEFECT_SIGMA_PX,
    SURFACE_PIXEL_SIZE_MM,
    SURFACE_SHAPE,
)

# Showcase slider default for both arms; steep-dome golden amp/sigma are
# make_steep_dome signature defaults (read via inspect so they can't drift).
_THETA_DEG = 30.0
_N_PSI = 4
_STEEP = inspect.signature(make_steep_dome).parameters
_STEEP_AMP_PX = float(_STEEP["amplitude_px"].default)
_STEEP_SIGMA_PX = float(_STEEP["sigma_px"].default)


def _b3a_config() -> ShowcaseConfig:
    """The B.3a headline config: inverse on, defect on, noise on."""
    geom = HybridGeometry(
        M=GEOMETRY_M,
        p=GEOMETRY_P_PX,
        a=GEOMETRY_A_PX,
        theta_projector=math.radians(_THETA_DEG),
        theta_camera=math.radians(_THETA_DEG),
    )
    return ShowcaseConfig.from_geometry(
        geom,
        surface_amplitude_px=_STEEP_AMP_PX,
        surface_sigma_px=_STEEP_SIGMA_PX,
        surface_shape=SURFACE_SHAPE,
        pixel_size_mm=SURFACE_PIXEL_SIZE_MM,
        defect_amplitude_px=STEEP_DEFECT_AMP_PX,
        defect_sigma_px=STEEP_DEFECT_SIGMA_PX,
        n_psi_steps=_N_PSI,
        noise_sigma=NOISE_SIGMA,
        noise_seed=NOISE_SEED,
        inverse_fpp_on=True,
        inject_defect_on=True,
        noise_on=True,
    )


def main() -> int:
    config = _b3a_config()
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    save_config(config, CONFIG_PATH)

    h = derive_b3a_headline(config)
    np.savez_compressed(
        NPZ_PATH,
        decoupling_int=np.int64(h["decoupling_int"]),
        error_ratio_int=np.int64(h["error_ratio_int"]),
        std_err=np.float64(h["std_err"]),
        max_abs=np.float64(h["max_abs"]),
        recovered=h["recovered"],
    )

    print(f"Wrote {CONFIG_PATH.relative_to(ROOT)}")
    print(f"Wrote {NPZ_PATH.relative_to(ROOT)}")
    print("Frozen B.3a headline:")
    print(f"  decoupling_int = {h['decoupling_int']}")
    print(f"  error_ratio_int = {h['error_ratio_int']}")
    print(f"  std_err  = {h['std_err']:.12e}")
    print(f"  max_abs  = {h['max_abs']:.12e}")
    rec = h["recovered"]
    print(
        f"  recovered: shape={rec.shape}, dtype={rec.dtype}, "
        f"min={float(rec.min()):.4e}, max={float(rec.max()):.4e}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
