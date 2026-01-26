"""Image sources for fringe projection systems."""

from .simulation import SimulationSource
from .camera import CameraSource, CameraBackend, DummyBackend
from .file import FileSource, save_frames

__all__ = [
    "SimulationSource",
    "CameraSource",
    "CameraBackend",
    "DummyBackend",
    "FileSource",
    "save_frames",
]
