"""Backends that stand behind the UI: the simulation today, the rig on hardware.

The UI talks only to a `Backend`'s methods (project / capture / reconstruct), so
swapping the simulation for real hardware is a construction choice -- made by
`create_backend()` from the `MP_BACKEND` env var -- not a rewrite. The concrete
`HardwareBackend` is imported lazily (via the factory) so the Qt/device code
under `hardware/` never loads in simulation mode.
"""
from __future__ import annotations

from backend.base import Backend, ReconstructionResult
from backend.factory import create_backend
from backend.simulation import SimulationBackend

__all__ = [
    "Backend",
    "ReconstructionResult",
    "SimulationBackend",
    "create_backend",
]
