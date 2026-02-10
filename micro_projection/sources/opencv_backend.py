"""OpenCV webcam backend for real camera acquisition."""

import sys
import numpy as np
from typing import Optional

from ..core.exceptions import AcquisitionError


class OpenCVBackend:
    """Camera backend using OpenCV VideoCapture.

    Works with USB webcams, DroidCam, and other OpenCV-compatible cameras.
    Returns float64 [0,1] grayscale frames to match SimulationSource convention.

    Args:
        device_index: Camera device index (0 for default camera)
        resolution: Optional (height, width) to request from camera
        backend_api: OpenCV backend API flag. Defaults to CAP_DSHOW on Windows.
    """

    def __init__(
        self,
        device_index: int = 0,
        resolution: Optional[tuple[int, int]] = None,
        backend_api: Optional[int] = None,
    ):
        self._device_index = device_index
        self._resolution = resolution
        self._backend_api = backend_api
        self._cap = None

    def connect(self) -> None:
        """Open the camera and verify it's working."""
        import cv2

        api = self._backend_api
        if api is None and sys.platform == "win32":
            api = cv2.CAP_DSHOW

        if api is not None:
            self._cap = cv2.VideoCapture(self._device_index, api)
        else:
            self._cap = cv2.VideoCapture(self._device_index)

        if not self._cap.isOpened():
            raise AcquisitionError(
                f"Failed to open camera at index {self._device_index}"
            )

        # Request resolution if specified
        if self._resolution is not None:
            h, w = self._resolution
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)

        # Verify with a test frame
        ret, frame = self._cap.read()
        if not ret or frame is None:
            self._cap.release()
            self._cap = None
            raise AcquisitionError("Camera opened but failed to read test frame")

    def disconnect(self) -> None:
        """Release the camera."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def grab_frame(self) -> np.ndarray:
        """Capture a single frame as float64 [0,1] grayscale.

        Returns:
            2D float64 array with values in [0, 1]
        """
        import cv2

        if self._cap is None or not self._cap.isOpened():
            raise AcquisitionError("Camera is not connected")

        ret, frame = self._cap.read()
        if not ret or frame is None:
            raise AcquisitionError("Failed to capture frame")

        # Convert BGR to grayscale
        if frame.ndim == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        # Normalize to float64 [0, 1]
        return gray.astype(np.float64) / 255.0

    def set_exposure(self, exposure_us: float) -> None:
        """Set exposure time in microseconds.

        Note: Many webcams and DroidCam may not support manual exposure
        through OpenCV. This method attempts to set it but may silently
        fail on unsupported cameras.
        """
        import cv2

        if self._cap is None:
            raise AcquisitionError("Camera is not connected")

        # Disable auto-exposure first
        self._cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # Manual mode
        # OpenCV exposure is typically in log2 units or device-specific
        self._cap.set(cv2.CAP_PROP_EXPOSURE, exposure_us)

    def get_resolution(self) -> tuple[int, int]:
        """Get current camera resolution as (height, width)."""
        import cv2

        if self._cap is None or not self._cap.isOpened():
            raise AcquisitionError("Camera is not connected")

        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return (h, w)

    def set_auto_exposure(self, enabled: bool) -> None:
        """Enable or disable auto-exposure.

        Note: DroidCam may not support this via OpenCV properties.
        The PhysicalSource class works around this by discarding
        initial frames after pattern changes.
        """
        import cv2

        if self._cap is None:
            raise AcquisitionError("Camera is not connected")

        if enabled:
            self._cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)  # Auto mode
        else:
            self._cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # Manual mode

    def grab_frame_averaged(self, n_frames: int = 5) -> np.ndarray:
        """Capture and average multiple frames for noise reduction.

        Args:
            n_frames: Number of frames to average

        Returns:
            2D float64 array with values in [0, 1]
        """
        accumulator = np.zeros_like(self.grab_frame())
        for _ in range(n_frames):
            accumulator += self.grab_frame()
        return accumulator / n_frames
