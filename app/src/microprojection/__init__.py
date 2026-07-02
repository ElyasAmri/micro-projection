"""Micro-projection control application.

Desktop GUI (PySide6) that drives the fringe-projection profilometry rig:
projector, camera, and the acquisition/reconstruction pipeline. This is a
ground-up rebuild; only the `microprojection.maestro` connector is carried
over from the previous app so a maestro agent can drive the UI unchanged.
"""
from __future__ import annotations

__version__ = "0.1.0"
