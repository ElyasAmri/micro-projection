"""Round-trip tests for the Stage 6 B.4.1 ShowcaseConfig serializer.

`conftest.py` puts `src/` on sys.path; `gui.main_window` needs the repo root
too (it does `from src.gui...` imports), so the two lines below add it. The B.3a
default VALUES are bound HERE (importing the live GUI constants) — io_utils.py
itself stays GUI-agnostic.
"""
from __future__ import annotations

import inspect
import json
import math
import os
import sys
from pathlib import Path

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from geometry import HybridGeometry  # noqa: E402
from io_utils import (  # noqa: E402
    CONFIG_SCHEMA_VERSION,
    ShowcaseConfig,
    load_config,
    save_config,
)
from test_surfaces import make_steep_dome  # noqa: E402
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

# Steep-dome golden amplitude/sigma are make_steep_dome SIGNATURE DEFAULTS, not
# named constants — read them via inspect so this reference tracks the source.
_STEEP_PARAMS = inspect.signature(make_steep_dome).parameters
_STEEP_AMP_PX = float(_STEEP_PARAMS["amplitude_px"].default)
_STEEP_SIGMA_PX = float(_STEEP_PARAMS["sigma_px"].default)

# Slider default for both arms in the B.3a showcase.
_THETA_DEG = 30.0


def _b3a_geometry() -> HybridGeometry:
    """The geometry _build_geometry constructs for the showcase."""
    return HybridGeometry(
        M=GEOMETRY_M,
        p=GEOMETRY_P_PX,
        a=GEOMETRY_A_PX,
        theta_projector=math.radians(_THETA_DEG),
        theta_camera=math.radians(_THETA_DEG),
    )


def _b3a_config() -> ShowcaseConfig:
    """Build the canonical B.3a headline config from the live defaults."""
    return ShowcaseConfig.from_geometry(
        _b3a_geometry(),
        surface_amplitude_px=_STEEP_AMP_PX,
        surface_sigma_px=_STEEP_SIGMA_PX,
        surface_shape=SURFACE_SHAPE,
        pixel_size_mm=SURFACE_PIXEL_SIZE_MM,
        defect_amplitude_px=STEEP_DEFECT_AMP_PX,
        defect_sigma_px=STEEP_DEFECT_SIGMA_PX,
        n_psi_steps=4,
        noise_sigma=NOISE_SIGMA,
        noise_seed=NOISE_SEED,
        inverse_fpp_on=True,
        inject_defect_on=True,
        noise_on=True,
    )


def test_showcase_config_roundtrips_exactly(tmp_path):
    """save -> load reproduces an equal config (JSON float round-trip is exact
    for float64; surface_shape restores to a tuple)."""
    cfg = _b3a_config()
    path = tmp_path / "ref_config.json"
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded == cfg


def test_loaded_geometry_recomputes_same_lambda_eq(tmp_path):
    """A geometry rebuilt from the reloaded config recomputes the IDENTICAL
    lambda_eq — proving the recompute-on-load path needs no serialized
    derived value, and matches a directly-built geometry."""
    cfg = _b3a_config()
    path = tmp_path / "ref_config.json"
    save_config(cfg, path)
    loaded = load_config(path)

    lam_loaded = loaded.to_geometry().equivalent_wavelength()
    assert lam_loaded == cfg.to_geometry().equivalent_wavelength()
    assert lam_loaded == _b3a_geometry().equivalent_wavelength()
    assert math.isfinite(lam_loaded)


def test_surface_shape_is_list_on_disk_tuple_in_memory(tmp_path):
    """JSON has no tuple type: surface_shape is a list on disk and a tuple
    after load."""
    cfg = _b3a_config()
    path = tmp_path / "c.json"
    save_config(cfg, path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["surface_shape"] == list(SURFACE_SHAPE)
    assert isinstance(raw["surface_shape"], list)

    loaded = load_config(path)
    assert isinstance(loaded.surface_shape, tuple)
    assert loaded.surface_shape == SURFACE_SHAPE


def test_schema_version_is_persisted(tmp_path):
    """schema_version travels to disk and back — versioning insurance for the
    hardware-phase reference."""
    cfg = _b3a_config()
    path = tmp_path / "c.json"
    save_config(cfg, path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == CONFIG_SCHEMA_VERSION
    assert load_config(path).schema_version == CONFIG_SCHEMA_VERSION


def test_to_dict_serializes_inputs_not_derived_lambda_eq():
    """The dict carries the geometry INPUT fields, and NOT the derived
    lambda_eq, the deliberate override, or the vestigial H/W/pixel_pitch_um."""
    d = _b3a_config().to_dict()
    for key in (
        "geometry_M", "geometry_p", "geometry_a",
        "theta_projector_rad", "theta_camera_rad",
    ):
        assert key in d
    for absent in (
        "lambda_eq", "lambda_eq_override", "H", "W", "pixel_pitch_um",
    ):
        assert absent not in d


def test_from_geometry_rejects_lambda_eq_override():
    """Capturing a geometry that carries a deliberate empirical override is
    rejected — we serialize inputs and recompute, never a stale derived value."""
    geom = HybridGeometry(
        M=GEOMETRY_M,
        p=GEOMETRY_P_PX,
        a=GEOMETRY_A_PX,
        theta_projector=math.radians(_THETA_DEG),
        theta_camera=math.radians(_THETA_DEG),
        lambda_eq_override=123.0,
    )
    with pytest.raises(ValueError, match="lambda_eq_override"):
        ShowcaseConfig.from_geometry(
            geom,
            surface_amplitude_px=_STEEP_AMP_PX,
            surface_sigma_px=_STEEP_SIGMA_PX,
            surface_shape=SURFACE_SHAPE,
            pixel_size_mm=SURFACE_PIXEL_SIZE_MM,
            defect_amplitude_px=STEEP_DEFECT_AMP_PX,
            defect_sigma_px=STEEP_DEFECT_SIGMA_PX,
            n_psi_steps=4,
            noise_sigma=NOISE_SIGMA,
            noise_seed=NOISE_SEED,
            inverse_fpp_on=True,
            inject_defect_on=True,
            noise_on=True,
        )
