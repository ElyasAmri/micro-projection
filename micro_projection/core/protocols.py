"""Abstract interfaces for fringe projection components."""

from typing import Protocol, runtime_checkable
import numpy as np

from .datatypes import PhaseMap


@runtime_checkable
class ImageSource(Protocol):
    """Abstract interface for image acquisition systems.

    This protocol defines the contract for any image source,
    whether simulation, real camera, or file-based replay.
    """

    def project_pattern(self, pattern: np.ndarray) -> None:
        """Project a pattern onto the surface.

        Args:
            pattern: 2D array representing the pattern to project.
                     Values should be in range [0, 1].
        """
        ...

    def capture_frame(self) -> np.ndarray:
        """Capture a single frame from the imaging system.

        Returns:
            2D array containing the captured image.
        """
        ...

    def get_resolution(self) -> tuple[int, int]:
        """Get the resolution of the imaging system.

        Returns:
            Tuple of (height, width) in pixels.
        """
        ...


@runtime_checkable
class FringeProcessor(Protocol):
    """Interface for processing captured fringe patterns."""

    def process(self, frames: list[np.ndarray]) -> PhaseMap:
        """Process a sequence of fringe images to extract phase.

        Args:
            frames: List of captured images with phase-shifted patterns.

        Returns:
            PhaseMap containing wrapped and optionally unwrapped phase.
        """
        ...


@runtime_checkable
class PhaseUnwrapper(Protocol):
    """Interface for phase unwrapping algorithms."""

    def unwrap(self, wrapped_phase: np.ndarray, quality: np.ndarray | None = None) -> np.ndarray:
        """Unwrap wrapped phase to continuous phase.

        Args:
            wrapped_phase: 2D array of wrapped phase in (-pi, pi]
            quality: Optional quality map for guided unwrapping

        Returns:
            2D array of unwrapped continuous phase.
        """
        ...


@runtime_checkable
class SurfaceFilter(Protocol):
    """Interface for surface filtering/separation algorithms."""

    def separate(self, height_map: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Separate surface into form and finish components.

        Args:
            height_map: 2D array of height values

        Returns:
            Tuple of (form, finish) arrays.
        """
        ...
