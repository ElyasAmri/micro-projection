"""The async capture interface, shared by simulation and hardware.

A capture turns a specimen into a directory of `frame_*.png` -- the simulation
does it by rendering with Blender out-of-process, hardware by projecting each
phase pattern and grabbing a camera frame. Both are asynchronous (they must not
block the GUI), and both report the same way: a `line` per progress message,
then exactly one terminal `finished(exit_code)` or `failed(message)`.

`CaptureController` is that common shape -- deliberately the same signal set as
`ui.process_runner.ProcessRunner`, so the main window drives either backend's
capture through one code path. Concrete controllers live with their backend
(`BlenderCapture` in backend.simulation, `HardwareCapture` in hardware.capture).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal


class CaptureController(QObject):
    """Base for an async capture. Emits `line` per progress message and exactly
    one of `finished(exit_code)` (0 == success) or `failed(message)`. After
    start() the concrete controller sets `capture_dir` and `n_steps` so the
    caller knows where the frames landed and how many to expect."""

    line = Signal(str)
    finished = Signal(int)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.capture_dir: Path | None = None
        self.n_steps: int = 0

    def is_running(self) -> bool:
        raise NotImplementedError

    def start(self, *, surface: str, n_steps: int, subdir: str,
              n_periods: float | None = None, **kwargs) -> None:
        """Begin capturing `surface` into out/app/<surface>/<subdir>. Extra
        kwargs are backend-specific (e.g. Blender `samples`, hardware
        `settle_ms`) and ignored where they don't apply."""
        raise NotImplementedError
