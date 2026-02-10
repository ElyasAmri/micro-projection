"""Combined physical source: projector + camera for real measurements."""

import numpy as np
from dataclasses import dataclass
from typing import Optional, Callable

from ..core.exceptions import AcquisitionError


@dataclass
class PhysicalConfig:
    """Configuration for physical measurement source.

    Attributes:
        settle_time_ms: Extra wait after pattern display (on top of projector settle)
        n_avg_frames: Number of frames to average per capture
        n_discard_frames: Frames to discard after pattern change (auto-exposure)
        pattern_resolution: Projector native resolution as (height, width)
    """
    settle_time_ms: float = 200.0
    n_avg_frames: int = 3
    n_discard_frames: int = 2
    pattern_resolution: tuple[int, int] = (1080, 1920)


class PhysicalSource:
    """Combined projector + camera source for physical fringe projection.

    Coordinates pattern display on a projector with frame capture from
    a camera. Handles frame discarding for auto-exposure settling and
    multi-frame averaging for noise reduction.

    Example:
        >>> backend = OpenCVBackend(device_index=0)
        >>> projector = CVProjector()
        >>> source = PhysicalSource(backend, projector)
        >>> with source:
        ...     frames = source.capture_sequence(patterns)
    """

    def __init__(
        self,
        camera_backend,
        projector,
        config: Optional[PhysicalConfig] = None,
    ):
        self._camera = camera_backend
        self._projector = projector
        self._config = config or PhysicalConfig()
        self._connected = False

    @property
    def config(self) -> PhysicalConfig:
        return self._config

    def connect(self) -> None:
        """Connect camera and open projector."""
        if self._connected:
            return
        try:
            self._camera.connect()
            self._projector.open()
            self._connected = True
        except Exception as e:
            # Clean up on partial failure
            try:
                self._camera.disconnect()
            except Exception:
                pass
            try:
                self._projector.close()
            except Exception:
                pass
            raise AcquisitionError(f"Failed to connect physical source: {e}")

    def disconnect(self) -> None:
        """Disconnect camera and close projector."""
        if not self._connected:
            return
        try:
            self._projector.close()
        except Exception:
            pass
        try:
            self._camera.disconnect()
        except Exception:
            pass
        self._connected = False

    def project_pattern(self, pattern: np.ndarray) -> None:
        """Display a pattern on the projector.

        Args:
            pattern: 2D array with values in [0, 1]
        """
        if not self._connected:
            raise AcquisitionError("Physical source is not connected")
        self._projector.display(pattern)

    def capture_frame(self) -> np.ndarray:
        """Capture a single frame with discarding and averaging.

        Discards n_discard_frames (auto-exposure settling), then
        averages n_avg_frames for noise reduction.

        Returns:
            2D float64 array with values in [0, 1]
        """
        if not self._connected:
            raise AcquisitionError("Physical source is not connected")

        # Discard initial frames (auto-exposure settling)
        for _ in range(self._config.n_discard_frames):
            self._camera.grab_frame()

        # Average multiple frames for noise reduction
        accumulator = None
        for _ in range(self._config.n_avg_frames):
            frame = self._camera.grab_frame()
            if accumulator is None:
                accumulator = frame.astype(np.float64)
            else:
                accumulator += frame

        return accumulator / self._config.n_avg_frames

    def get_resolution(self) -> tuple[int, int]:
        """Get camera resolution (the measurement grid).

        Returns:
            (height, width) of the camera sensor
        """
        return self._camera.get_resolution()

    def capture_sequence(
        self,
        patterns: list[np.ndarray],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[np.ndarray]:
        """Project patterns and capture frames sequentially.

        This is the main workhorse method. For each pattern:
        1. Display pattern on projector (with settle time)
        2. Discard frames for auto-exposure settling
        3. Average frames for noise reduction

        Args:
            patterns: List of 2D pattern arrays with values in [0, 1]
            progress_callback: Optional callback(current, total) for progress

        Returns:
            List of captured frames (same length as patterns)
        """
        if not self._connected:
            raise AcquisitionError("Physical source is not connected")

        frames = []
        total = len(patterns)

        for i, pattern in enumerate(patterns):
            if progress_callback is not None:
                progress_callback(i, total)

            # Project pattern (projector handles settle time internally)
            self.project_pattern(pattern)

            # Capture with discard + averaging
            frame = self.capture_frame()
            frames.append(frame)

        if progress_callback is not None:
            progress_callback(total, total)

        return frames

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False
