"""Phase-shifting fringe acquisition.

Projects a sinusoidal fringe stepped through ``num_phases`` equal phase shifts
across one period (the classic N-step phase-shifting profilometry input) and
captures one frame per step, then saves the set. The frame count and fringe
period are configurable; the steps themselves may change as the processing
side firms up.
"""
from __future__ import annotations

import os

import numpy as np

from microprojection.patterns import fringe
from microprojection.pipelines.base import CapturePipeline
from microprojection.pipelines.frame_io import save_frame


class PhaseShiftPipeline(CapturePipeline):
    def __init__(self, camera, projector_window, settings, output_dir, *,
                 num_phases: int = 8, period: float = 32.0,
                 orientation: str = "vertical", parent=None):
        super().__init__(camera, projector_window, settings, output_dir,
                         parent=parent)
        self._num_phases = max(1, int(num_phases))
        self._period = period
        self._orientation = orientation
        self._frames: list[np.ndarray] = []

    @property
    def total(self) -> int:
        return self._num_phases

    def pattern_for(self, i: int):
        # One equal phase step per frame across a full 2*pi period.
        phase = 2.0 * np.pi * i / self._num_phases
        return fringe(self.width, self.height, period=self._period,
                      orientation=self._orientation, phase=phase)

    def handle_frame(self, i: int, frame) -> None:
        self._frames.append(np.asarray(frame.image).copy())

    def finalize(self) -> None:
        for i, image in enumerate(self._frames):
            save_frame(os.path.join(self._output_dir, f"phase_{i:02d}.png"), image)
