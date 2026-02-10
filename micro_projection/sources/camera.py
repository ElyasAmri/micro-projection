"""Real camera adapter for fringe projection systems.

This module provides a placeholder for integrating real camera hardware.
Actual implementations would depend on the specific camera SDK being used
(e.g., Basler Pylon, FLIR Spinnaker, OpenCV VideoCapture, etc.).
"""

import numpy as np
from typing import Optional, Protocol, Any

from ..core.exceptions import AcquisitionError, ConfigurationError


class CameraBackend(Protocol):
    """Protocol for camera backend implementations.

    Implement this protocol to integrate a specific camera SDK.
    """

    def connect(self) -> None:
        """Establish connection to camera hardware."""
        ...

    def disconnect(self) -> None:
        """Disconnect from camera hardware."""
        ...

    def grab_frame(self) -> np.ndarray:
        """Capture a single frame."""
        ...

    def set_exposure(self, exposure_us: float) -> None:
        """Set exposure time in microseconds."""
        ...

    def get_resolution(self) -> tuple[int, int]:
        """Get sensor resolution (height, width)."""
        ...


class CameraSource:
    """Real camera source for fringe projection.

    This class wraps camera hardware through a backend interface,
    providing the same ImageSource protocol as SimulationSource.

    Example (with a hypothetical backend):
        >>> backend = OpenCVBackend(camera_index=0)
        >>> camera = CameraSource(backend)
        >>> camera.connect()
        >>> frame = camera.capture_frame()
        >>> camera.disconnect()
    """

    def __init__(self, backend: CameraBackend):
        """Initialize camera source with a backend.

        Args:
            backend: Camera backend implementation
        """
        self._backend = backend
        self._connected = False
        self._current_pattern: Optional[np.ndarray] = None
        self._projector: Optional[Any] = None

    def connect(self) -> None:
        """Connect to the camera hardware."""
        if self._connected:
            return

        try:
            self._backend.connect()
            self._connected = True
        except Exception as e:
            raise AcquisitionError(f"Failed to connect to camera: {e}")

    def disconnect(self) -> None:
        """Disconnect from the camera hardware."""
        if not self._connected:
            return

        try:
            self._backend.disconnect()
            self._connected = False
        except Exception as e:
            raise AcquisitionError(f"Failed to disconnect from camera: {e}")

    def set_projector(self, projector: Any) -> None:
        """Set the projector device for pattern projection.

        Args:
            projector: Projector device or display interface
        """
        self._projector = projector

    def project_pattern(self, pattern: np.ndarray) -> None:
        """Project a pattern using the configured projector.

        Note: In a real implementation, this would display the pattern
        on a DLP projector, LCD display, or similar device.

        Args:
            pattern: 2D array with values in [0, 1]
        """
        self._current_pattern = pattern.copy()

        if self._projector is not None:
            self._projector.display(pattern)
        else:
            # Without a projector, we just store the pattern
            # User must manually display/project it
            pass

    def capture_frame(self) -> np.ndarray:
        """Capture a single frame from the camera.

        Returns:
            2D array of captured image (grayscale) or 3D for color

        Raises:
            AcquisitionError: If camera is not connected or capture fails
        """
        if not self._connected:
            raise AcquisitionError("Camera is not connected")

        try:
            frame = self._backend.grab_frame()
            return frame
        except Exception as e:
            raise AcquisitionError(f"Failed to capture frame: {e}")

    def get_resolution(self) -> tuple[int, int]:
        """Get camera resolution.

        Returns:
            Tuple of (height, width) in pixels
        """
        return self._backend.get_resolution()

    def set_exposure(self, exposure_us: float) -> None:
        """Set camera exposure time.

        Args:
            exposure_us: Exposure time in microseconds
        """
        if not self._connected:
            raise ConfigurationError("Camera must be connected to set exposure")

        self._backend.set_exposure(exposure_us)

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False


class DummyBackend:
    """Dummy backend for testing without real hardware.

    Returns synthetic test images instead of real camera data.
    """

    def __init__(self, resolution: tuple[int, int] = (512, 512)):
        self._resolution = resolution
        self._exposure = 10000.0  # microseconds

    def connect(self) -> None:
        """Simulate connection."""
        pass

    def disconnect(self) -> None:
        """Simulate disconnection."""
        pass

    def grab_frame(self) -> np.ndarray:
        """Return a dummy test frame."""
        height, width = self._resolution
        # Return a simple gradient for testing
        y, x = np.mgrid[0:height, 0:width]
        return (x / width * 255).astype(np.uint8)

    def set_exposure(self, exposure_us: float) -> None:
        """Store exposure value."""
        self._exposure = exposure_us

    def get_resolution(self) -> tuple[int, int]:
        """Return configured resolution."""
        return self._resolution
