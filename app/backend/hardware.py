"""The hardware backend: a real projector + camera behind the same interface
the simulation uses.

Projection pushes the fringe to the projector screen; capture projects the
phase sequence and grabs frames (see hardware.capture); reconstruction is the
shared, sim-provided maths (a real target has no ground truth, so only a height
map comes out). The Qt widgets and device SDK live under `hardware/` and are
imported lazily, so importing this module -- or running the app in simulation
mode -- never touches them.
"""
from __future__ import annotations

import numpy as np

from backend.base import Backend, out_root
from logbus import get_logger

log = get_logger("hardware")

# The single physical target under the rig. The UI still shows a "specimen"
# selector; on hardware there's just the one thing under the camera.
LIVE_TARGET = "live"


class HardwareBackend(Backend):
    """Drives the fringe-projection loop against the real projector + camera."""

    kind = "hardware"
    kind_label = "Hardware"

    def __init__(self, n_periods: float = 8.0) -> None:
        super().__init__(n_periods)
        self._projector = None  # hardware.projector.ProjectorController, lazy

    # -- projection ----------------------------------------------------------

    def _get_projector(self):
        if self._projector is None:
            from hardware.projector import ProjectorController

            self._projector = ProjectorController()
        return self._projector

    def project(self, fringe: np.ndarray) -> None:
        """Display the fringe on the physical projector screen."""
        self._get_projector().show(fringe)

    # -- specimens / capture -------------------------------------------------

    def available_surfaces(self) -> list[str]:
        return [LIVE_TARGET]

    def new_capture_controller(self, parent=None):
        from hardware.camera import open_camera
        from hardware.capture import HardwareCapture

        return HardwareCapture(
            self._get_projector(), open_camera, self.n_periods, out_root(), parent
        )

    def shutdown(self) -> None:
        """Close the projector window (call on app exit)."""
        if self._projector is not None:
            self._projector.close()
            self._projector = None
