"""The camera settings the rig runs with -- one shared, explicit record.

`CameraSettings` is what the Camera Settings panel edits and what
`SpinnakerCamera` pushes to the device every time it opens (per capture), so
the camera state is reproducible instead of whatever the device last held.
Values are clamped to the camera's own limits at apply time, so out-of-range
entries degrade gracefully.

This module is deliberately dependency-free (no Qt, no PySpin) so the UI can
import it at startup without touching the SDK: the panel writes here, the
capture worker reads here, and persistence (QSettings) stays in the UI layer.

Defaults are metrology-first: gamma stays off (the phase-shift maths assumes
the sinusoid is imaged linearly) and `MP_CAM_EXPOSURE_US`, when set, seeds a
fixed exposure exactly as before the panel existed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CameraSettings:
    """A full camera configuration; applied at the start of every capture."""

    exposure_auto: bool = True     # continuous auto-exposure (off for scans!)
    exposure_us: float = 20000.0   # fixed exposure, when exposure_auto is off
    gain_auto: bool = True         # continuous auto-gain (FLIR factory default)
    gain_db: float = 0.0           # fixed analog gain, when gain_auto is off
    gamma_enabled: bool = False    # keep off: gamma breaks fringe linearity
    gamma: float = 1.0             # gamma value, when enabled
    black_level_pct: float = 0.0   # sensor black level offset (percent)


def default_camera_settings() -> CameraSettings:
    """The out-of-the-box settings. `MP_CAM_EXPOSURE_US` (the pre-panel way to
    fix the exposure) still works: when set, it seeds a fixed exposure."""
    exposure_us = os.environ.get("MP_CAM_EXPOSURE_US")
    if exposure_us:
        try:
            return CameraSettings(exposure_auto=False, exposure_us=float(exposure_us))
        except ValueError:
            pass  # a malformed value falls through to plain defaults
    return CameraSettings()


_current: CameraSettings | None = None  # None until the app/panel first sets it


def get_camera_settings() -> CameraSettings:
    """The settings the next camera open will apply."""
    return _current if _current is not None else default_camera_settings()


def set_camera_settings(settings: CameraSettings) -> None:
    """Swap in a new configuration (takes effect at the next capture -- the
    camera is opened fresh, and configured, per capture run)."""
    global _current
    _current = settings
