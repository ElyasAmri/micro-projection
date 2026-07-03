"""Pick the backend the app runs against.

`MP_BACKEND` selects it: 'sim' (default), 'hardware', or 'auto'. 'auto' uses the
hardware backend if a FLIR camera is actually attached, else the simulation --
so the same build runs on a dev machine and on the rig without a code change,
and plugging the camera in is enough to go live.
"""
from __future__ import annotations

import os

from backend.base import Backend
from backend.simulation import SimulationBackend
from logbus import get_logger

log = get_logger("backend")


def create_backend(kind: str | None = None) -> Backend:
    kind = (kind or os.environ.get("MP_BACKEND") or "sim").strip().lower()

    if kind in ("hardware", "hw", "rig", "real"):
        return _hardware()
    if kind == "auto":
        try:
            from hardware.camera import has_spinnaker_camera

            if has_spinnaker_camera():
                return _hardware()
        except Exception as exc:  # noqa: BLE001 - probing must never crash startup
            log.warning(f"hardware probe failed ({exc}); using the simulation")
        return SimulationBackend()
    if kind not in ("sim", "simulation"):
        log.warning(f"unknown MP_BACKEND={kind!r}; using the simulation")
    return SimulationBackend()


def _hardware() -> Backend:
    from backend.hardware import HardwareBackend

    return HardwareBackend()
