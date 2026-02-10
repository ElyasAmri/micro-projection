"""Fullscreen pattern display for fringe projection."""

import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class ProjectorConfig:
    """Configuration for the fullscreen pattern projector.

    Attributes:
        window_name: OpenCV window name
        screen_index: Monitor index for multi-monitor setups
        resolution: Display resolution as (height, width), None for auto
        settle_time_ms: Wait time after displaying pattern (ms)
        fullscreen: Whether to use fullscreen mode
        gamma: Gamma correction value (1.0 = no correction)
    """
    window_name: str = "Projector"
    screen_index: int = 0
    resolution: Optional[tuple[int, int]] = None
    settle_time_ms: float = 200.0
    fullscreen: bool = True
    gamma: float = 1.0


class CVProjector:
    """Fullscreen pattern display using OpenCV highgui.

    Displays fringe patterns fullscreen on a specified monitor.
    Handles float-to-uint8 conversion, gamma correction, and
    provides settle time for camera auto-exposure adjustment.

    Example:
        >>> projector = CVProjector()
        >>> with projector:
        ...     projector.display(pattern)
    """

    def __init__(self, config: Optional[ProjectorConfig] = None):
        self._config = config or ProjectorConfig()
        self._window_created = False
        self._display_resolution: Optional[tuple[int, int]] = None

    @property
    def config(self) -> ProjectorConfig:
        return self._config

    def open(self) -> None:
        """Create the fullscreen display window."""
        import cv2

        name = self._config.window_name

        if self._config.fullscreen:
            cv2.namedWindow(name, cv2.WINDOW_NORMAL)
            cv2.setWindowProperty(
                name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN
            )
        else:
            cv2.namedWindow(name, cv2.WINDOW_AUTOSIZE)

        # Move window to the correct monitor if specified
        if self._config.screen_index > 0:
            # Approximate: assume monitors are side-by-side horizontally
            # User may need to adjust this for their specific monitor layout
            x_offset = self._config.screen_index * 1920
            cv2.moveWindow(name, x_offset, 0)

        self._window_created = True

        # Determine display resolution
        if self._config.resolution is not None:
            self._display_resolution = self._config.resolution
        else:
            # Display a small test image to let OpenCV figure out the window
            test = np.zeros((100, 100), dtype=np.uint8)
            cv2.imshow(name, test)
            cv2.waitKey(1)
            self._display_resolution = None  # Will use pattern size directly

    def close(self) -> None:
        """Destroy the display window."""
        import cv2

        if self._window_created:
            cv2.destroyWindow(self._config.window_name)
            cv2.waitKey(1)
            self._window_created = False
            self._display_resolution = None

    def display(self, pattern: np.ndarray) -> None:
        """Display a pattern on the projector.

        Handles:
        - float [0,1] to uint8 conversion
        - Gamma correction
        - Resizing to display resolution
        - Settle time wait (via cv2.waitKey)

        Args:
            pattern: 2D array with values in [0, 1]
        """
        import cv2

        if not self._window_created:
            self.open()

        # Apply gamma correction
        if self._config.gamma != 1.0:
            pattern = np.clip(pattern, 0, 1)
            pattern = np.power(pattern, 1.0 / self._config.gamma)

        # Convert to uint8
        img = np.clip(pattern * 255.0, 0, 255).astype(np.uint8)

        # Resize to display resolution if specified
        if self._display_resolution is not None:
            h, w = self._display_resolution
            if img.shape != (h, w):
                img = cv2.resize(img, (w, h), interpolation=cv2.INTER_LINEAR)

        cv2.imshow(self._config.window_name, img)

        # waitKey serves double duty: processes GUI events + settle time
        wait_ms = max(1, int(self._config.settle_time_ms))
        cv2.waitKey(wait_ms)

    def get_resolution(self) -> Optional[tuple[int, int]]:
        """Get the display resolution as (height, width), or None if auto."""
        return self._display_resolution

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
