"""File-based image source for loading saved fringe images.

Useful for:
- Testing and development without hardware
- Replaying captured datasets
- Debugging processing pipelines with known inputs
"""

import numpy as np
from pathlib import Path
from typing import Sequence, Optional, Iterator

from ..core.exceptions import AcquisitionError, ConfigurationError


class FileSource:
    """Load fringe images from files for testing and replay.

    Supports loading single images or sequences of phase-shifted images
    from common image formats (PNG, TIFF, NPY, etc.).

    Example:
        >>> source = FileSource()
        >>> source.load_sequence("captures/seq_*.png")
        >>> for frame in source:
        ...     process(frame)

    Example with explicit files:
        >>> source = FileSource()
        >>> source.load_files([
        ...     "phase_0.png",
        ...     "phase_90.png",
        ...     "phase_180.png",
        ...     "phase_270.png"
        ... ])
    """

    def __init__(self):
        """Initialize the file source."""
        self._frames: list[np.ndarray] = []
        self._current_index: int = 0
        self._resolution: Optional[tuple[int, int]] = None
        self._file_paths: list[Path] = []

    def load_file(self, path: str | Path) -> np.ndarray:
        """Load a single image file.

        Args:
            path: Path to image file (PNG, TIFF, NPY, etc.)

        Returns:
            Loaded image as numpy array

        Raises:
            AcquisitionError: If file cannot be loaded
        """
        path = Path(path)

        if not path.exists():
            raise AcquisitionError(f"File not found: {path}")

        try:
            if path.suffix.lower() == '.npy':
                frame = np.load(path)
            elif path.suffix.lower() == '.npz':
                data = np.load(path)
                # Assume first array in archive
                frame = data[list(data.keys())[0]]
            else:
                # Use imageio for standard image formats
                try:
                    import imageio.v3 as iio
                    frame = iio.imread(path)
                except ImportError:
                    # Fallback to PIL
                    from PIL import Image
                    frame = np.array(Image.open(path))

            # Convert to grayscale if color
            if frame.ndim == 3:
                if frame.shape[2] == 3:
                    # RGB to grayscale
                    frame = np.mean(frame, axis=2)
                elif frame.shape[2] == 4:
                    # RGBA to grayscale
                    frame = np.mean(frame[:, :, :3], axis=2)

            # Normalize to [0, 1] if integer type
            if frame.dtype in (np.uint8, np.uint16):
                frame = frame.astype(np.float64) / np.iinfo(frame.dtype).max

            return frame.astype(np.float64)

        except Exception as e:
            raise AcquisitionError(f"Failed to load image {path}: {e}")

    def load_files(self, paths: Sequence[str | Path]) -> None:
        """Load multiple image files as a sequence.

        Args:
            paths: Sequence of paths to image files

        Raises:
            ConfigurationError: If images have inconsistent shapes
        """
        self._frames = []
        self._file_paths = []
        self._resolution = None

        for path in paths:
            frame = self.load_file(path)

            if self._resolution is None:
                self._resolution = frame.shape[:2]
            elif frame.shape[:2] != self._resolution:
                raise ConfigurationError(
                    f"Image {path} has shape {frame.shape[:2]}, "
                    f"expected {self._resolution}"
                )

            self._frames.append(frame)
            self._file_paths.append(Path(path))

        self._current_index = 0

    def load_sequence(self, pattern: str, sort: bool = True) -> None:
        """Load images matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., "captures/*.png", "seq_*.tiff")
            sort: If True, sort files alphabetically

        Example:
            >>> source.load_sequence("phase_*.png")  # Loads phase_0.png, phase_1.png, etc.
        """
        from glob import glob

        paths = glob(pattern)

        if not paths:
            raise AcquisitionError(f"No files match pattern: {pattern}")

        if sort:
            paths = sorted(paths)

        self.load_files(paths)

    def load_directory(
        self,
        directory: str | Path,
        extensions: Sequence[str] = ('.png', '.tiff', '.tif', '.npy'),
        sort: bool = True,
    ) -> None:
        """Load all images from a directory.

        Args:
            directory: Path to directory containing images
            extensions: File extensions to include
            sort: If True, sort files alphabetically
        """
        directory = Path(directory)

        if not directory.is_dir():
            raise AcquisitionError(f"Not a directory: {directory}")

        paths = []
        for ext in extensions:
            paths.extend(directory.glob(f"*{ext}"))
            paths.extend(directory.glob(f"*{ext.upper()}"))

        if not paths:
            raise AcquisitionError(f"No images found in {directory}")

        if sort:
            paths = sorted(paths)

        self.load_files(paths)

    def project_pattern(self, pattern: np.ndarray) -> None:
        """No-op for file source (patterns are already in loaded images).

        This method exists for interface compatibility with ImageSource protocol.
        """
        pass

    def capture_frame(self) -> np.ndarray:
        """Return the next frame in the sequence.

        Returns:
            Next image in the loaded sequence

        Raises:
            AcquisitionError: If no images loaded or sequence exhausted
        """
        if not self._frames:
            raise AcquisitionError("No images loaded")

        if self._current_index >= len(self._frames):
            raise AcquisitionError("No more frames in sequence")

        frame = self._frames[self._current_index]
        self._current_index += 1
        return frame

    def get_resolution(self) -> tuple[int, int]:
        """Get the resolution of loaded images.

        Returns:
            Tuple of (height, width) in pixels

        Raises:
            ConfigurationError: If no images loaded
        """
        if self._resolution is None:
            raise ConfigurationError("No images loaded")
        return self._resolution

    def get_all_frames(self) -> list[np.ndarray]:
        """Get all loaded frames at once.

        Returns:
            List of all loaded images
        """
        return self._frames.copy()

    def reset(self) -> None:
        """Reset the frame index to the beginning."""
        self._current_index = 0

    def __len__(self) -> int:
        """Return number of loaded frames."""
        return len(self._frames)

    def __iter__(self) -> Iterator[np.ndarray]:
        """Iterate over loaded frames."""
        self.reset()
        return self

    def __next__(self) -> np.ndarray:
        """Return next frame in iteration."""
        if self._current_index >= len(self._frames):
            raise StopIteration
        return self.capture_frame()

    def __getitem__(self, index: int) -> np.ndarray:
        """Get frame by index."""
        return self._frames[index]


def save_frames(
    frames: Sequence[np.ndarray],
    directory: str | Path,
    prefix: str = "frame",
    format: str = "png",
) -> list[Path]:
    """Save frames to files for later replay.

    Args:
        frames: Sequence of images to save
        directory: Output directory
        prefix: Filename prefix
        format: Output format (png, tiff, npy)

    Returns:
        List of saved file paths
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    saved_paths = []

    for i, frame in enumerate(frames):
        filename = f"{prefix}_{i:04d}.{format}"
        path = directory / filename

        if format == 'npy':
            np.save(path, frame)
        else:
            # Convert to uint16 for better precision
            if frame.max() <= 1.0:
                frame_int = (frame * 65535).astype(np.uint16)
            else:
                frame_int = frame.astype(np.uint16)

            try:
                import imageio.v3 as iio
                iio.imwrite(path, frame_int)
            except ImportError:
                from PIL import Image
                Image.fromarray(frame_int).save(path)

        saved_paths.append(path)

    return saved_paths
