"""Backends that stand behind the UI: today the simulation, later the rig.

The UI talks only to a backend's methods (project / reconstruct / ...), so
swapping the simulation for real hardware is a construction choice, not a
rewrite.
"""
from __future__ import annotations

from backend.simulation import ReconstructionResult, SimulationBackend

__all__ = ["SimulationBackend", "ReconstructionResult"]
