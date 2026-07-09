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
        self._service = None  # hardware.camera_service.CameraService, lazy

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

    def camera_service(self):
        """The persistent camera service (started on first use). The camera is
        opened once and held for the app's lifetime; captures and the live
        view borrow frames from it (see hardware.camera_service)."""
        if self._service is None:
            import atexit

            from hardware.camera import open_camera
            from hardware.camera_service import CameraService

            self._service = CameraService(open_camera(n_periods=self.n_periods))
            self._service.start()
            # Safety net: never let the interpreter exit with the service
            # thread running (stop_service is idempotent; shutdown() calls it
            # first in the normal path).
            atexit.register(self._service.stop_service)
        return self._service

    def projector_size(self) -> tuple:
        """The projector's pixel size (patterns map 1:1 at this resolution)."""
        return self._get_projector().screen_size()

    def apply_camera_settings_live(self) -> None:
        """Push the shared CameraSettings to the camera if it is already open.
        A service that was never started needs nothing: settings are applied
        when it first opens the device."""
        if self._service is not None:
            self._service.request_apply_settings()

    def new_capture_controller(self, parent=None):
        from hardware.capture import HardwareCapture

        # The service is passed as a provider (the bound method), not started
        # here: the camera should open on first actual use, once the app is
        # up and idle -- opening it mid-construction has crashed the SDK.
        return HardwareCapture(
            self._get_projector(), self.camera_service, self.n_periods,
            out_root(), parent
        )

    def shutdown(self) -> None:
        """Stop the camera service and close the projector (call on app exit)."""
        if self._service is not None:
            self._service.stop_service()
            self._service = None
        if self._projector is not None:
            self._projector.close()
            self._projector = None
