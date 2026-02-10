"""Image sources for fringe projection systems."""

from .simulation import SimulationSource
from .camera import CameraSource, CameraBackend, DummyBackend
from .file import FileSource, save_frames
from .projector import CVProjector, ProjectorConfig
from .physical import PhysicalSource, PhysicalConfig

__all__ = [
    "SimulationSource",
    "CameraSource",
    "CameraBackend",
    "DummyBackend",
    "FileSource",
    "save_frames",
    "CVProjector",
    "ProjectorConfig",
    "PhysicalSource",
    "PhysicalConfig",
]
