"""The rig camera: a minimal grab interface with three implementations.

The rig uses a FLIR/Teledyne machine-vision camera through the Spinnaker SDK
(`PySpin`). PySpin is imported lazily and its absence is non-fatal -- on a dev
machine without the SDK the app simply doesn't offer that backend. Two
fallbacks keep the hardware path runnable off the rig:

  * `SpinnakerCamera` -- the real camera (Mono8, fixed or auto exposure).
  * `OpenCVCamera`    -- any USB/UVC webcam, for a quick bench stand-in.
  * `DummyCamera`     -- synthesises a phase-stepped fringe frame, so the whole
                         project -> capture -> reconstruct loop runs with no
                         hardware at all (used for tests and offline demos).

Every `grab()` returns a freshly exposed (H, W) uint8 grayscale ndarray. Choose
one with `open_camera()`, which honours `MP_CAMERA` (spinnaker|opencv|dummy|auto).
"""
from __future__ import annotations

import gc
import os
from abc import ABC, abstractmethod

import numpy as np

from hardware.camera_config import CameraSettings, get_camera_settings
from logbus import get_logger

log = get_logger("camera")


try:  # optional: only present on a machine with the Spinnaker SDK installed
    import PySpin  # type: ignore

    HAS_PYSPIN = True
except ImportError:
    PySpin = None  # type: ignore
    HAS_PYSPIN = False


class Camera(ABC):
    """A camera that yields single grayscale frames on demand."""

    name: str = "camera"

    @abstractmethod
    def open(self) -> None:
        """Acquire the device and start acquisition."""

    @abstractmethod
    def grab(self) -> np.ndarray:
        """Return the most recent frame as an (H, W) uint8 grayscale array."""

    @abstractmethod
    def close(self) -> None:
        """Stop acquisition and release the device."""

    def set_sequence(self, n_steps: int) -> None:
        """Hint the length of the coming phase-shift sequence. Real cameras
        ignore it; the synthetic camera uses it to phase its frames."""

    def __enter__(self) -> "Camera":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class SpinnakerCamera(Camera):
    """A FLIR/Teledyne camera via PySpin. Grabs Mono8 frames, configured from
    the shared `CameraSettings` (the Camera Settings panel; the pre-panel
    MP_CAM_EXPOSURE_US still seeds a fixed exposure -- recommended for
    phase-shifting, so every step is imaged at identical brightness).

    `grab()` returns the newest frame: the stream is set to NewestOnly buffer
    handling, so after the projector changes pattern and we let it settle, the
    frame we read is one taken *after* the change, not a stale buffered one."""

    def __init__(self, index: int = 0) -> None:
        self.index = index
        self.name = f"FLIR camera #{index}"
        self._system = None
        self._cam_list = None
        self._cam = None

    def open(self) -> None:
        if not HAS_PYSPIN:
            raise RuntimeError("PySpin (Spinnaker SDK) is not installed")
        try:
            self._open_device()
        except PySpin.SpinnakerException as exc:
            # Do NOT retry: re-initializing the SDK in-process after a failed
            # open aborts the whole process (observed live). A -1004 here
            # means the camera is held elsewhere: another process, or a
            # killed one whose driver handle has not been reaped yet.
            self.close()
            raise RuntimeError(
                f"could not open the camera ({exc}); it is likely held by "
                "another process or by a recently killed one. Close SpinView "
                "if open, wait a minute, or replug the camera USB") from exc
        log.info(f"opened {self.name} (Mono8)")

    def _open_device(self) -> None:
        self._system = PySpin.System.GetInstance()
        self._cam_list = self._system.GetCameras()
        if self.index >= self._cam_list.GetSize():
            self._release_system()
            raise RuntimeError(f"FLIR camera index {self.index} not found")
        cam = self._cam_list[self.index]
        self._cam = cam
        cam.Init()
        try:
            self._configure(cam)
            cam.BeginAcquisition()
        except Exception:
            self.close()
            raise

    def _configure(self, cam) -> None:
        cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)
        cam.PixelFormat.SetValue(PySpin.PixelFormat_Mono8)

        # Always keep only the freshest frame in the buffer.
        try:
            snode = cam.GetTLStreamNodeMap()
            handling = PySpin.CEnumerationPtr(snode.GetNode("StreamBufferHandlingMode"))
            newest = handling.GetEntryByName("NewestOnly")
            if PySpin.IsAvailable(newest) and PySpin.IsReadable(newest):
                handling.SetIntValue(newest.GetValue())
        except PySpin.SpinnakerException:
            pass

        self._apply_settings(cam, get_camera_settings())

    def _apply_settings(self, cam, s: CameraSettings) -> None:
        """Push the shared `CameraSettings` to the device, clamping each value
        to the camera's own limits. Exposure failures abort the open (a scan at
        an unknown exposure is worthless); the rest are best-effort per feature,
        so one unsupported node doesn't take down the capture."""
        if s.exposure_auto:
            cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Continuous)
        else:
            cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
            cam.ExposureMode.SetValue(PySpin.ExposureMode_Timed)
            value = self._clamp(cam.ExposureTime, s.exposure_us)
            cam.ExposureTime.SetValue(value)
            log.info(f"exposure fixed at {value:.0f} us")

        try:
            if s.gain_auto:
                cam.GainAuto.SetValue(PySpin.GainAuto_Continuous)
            else:
                cam.GainAuto.SetValue(PySpin.GainAuto_Off)
                value = self._clamp(cam.Gain, s.gain_db)
                cam.Gain.SetValue(value)
                log.info(f"gain fixed at {value:.1f} dB")
        except PySpin.SpinnakerException as exc:
            log.warning(f"could not set gain: {exc}")

        try:
            cam.GammaEnable.SetValue(bool(s.gamma_enabled))
            if s.gamma_enabled:
                cam.Gamma.SetValue(self._clamp(cam.Gamma, s.gamma))
        except PySpin.SpinnakerException as exc:
            log.warning(f"could not set gamma: {exc}")

        try:
            cam.BlackLevelSelector.SetValue(PySpin.BlackLevelSelector_All)
            cam.BlackLevel.SetValue(self._clamp(cam.BlackLevel, s.black_level_pct))
        except PySpin.SpinnakerException as exc:
            log.warning(f"could not set black level: {exc}")

    @staticmethod
    def _clamp(node, value: float) -> float:
        """`value` limited to a device node's [GetMin, GetMax] range."""
        return max(node.GetMin(), min(float(value), node.GetMax()))

    def grab(self) -> np.ndarray:
        image = self._cam.GetNextImage(2000)  # ms timeout
        try:
            if image.IsIncomplete():
                raise RuntimeError(
                    f"incomplete frame ({image.GetImageStatus()})")
            return np.asarray(image.GetNDArray(), dtype=np.uint8).copy()
        finally:
            image.Release()

    def close(self) -> None:
        try:
            if self._cam is not None:
                try:
                    self._cam.EndAcquisition()
                except Exception:  # noqa: BLE001 - may not be acquiring
                    pass
                try:
                    self._cam.DeInit()
                except Exception:  # noqa: BLE001
                    pass
        finally:
            self._cam = None
            # Collect any lingering proxy references (e.g. held by exception
            # tracebacks) before releasing the SDK; Spinnaker refuses to clear
            # a camera that anything still references (error -1004).
            gc.collect()
            self._release_system()

    def _release_system(self) -> None:
        # Failures here are logged, not swallowed silently: a refused Clear or
        # ReleaseInstance leaves the SDK holding the device, which is exactly
        # the state that breaks the next open.
        if self._cam_list is not None:
            try:
                self._cam_list.Clear()
            except Exception as exc:  # noqa: BLE001 - report and continue
                log.warning(f"camera list clear failed: {exc}")
            self._cam_list = None
        if self._system is not None:
            try:
                self._system.ReleaseInstance()
            except Exception as exc:  # noqa: BLE001 - report and continue
                log.warning(f"camera system release failed: {exc}")
            self._system = None


class OpenCVCamera(Camera):
    """Any USB/UVC webcam via OpenCV -- a quick stand-in on the bench. Reads a
    few frames per grab to flush the driver's buffer so the returned frame
    reflects the current projection."""

    def __init__(self, index: int = 0) -> None:
        self.index = index
        self.name = f"USB camera #{index}"
        self._cap = None

    def open(self) -> None:
        import cv2

        cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(f"could not open USB camera #{self.index}")
        self._cap = cap
        log.info(f"opened {self.name}")

    def grab(self) -> np.ndarray:
        import cv2

        frame = None
        for _ in range(5):  # flush buffered frames -> newest reflects the pattern
            ok, frame = self._cap.read()
        if frame is None:
            raise RuntimeError("USB camera returned no frame")
        if frame.ndim == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return np.ascontiguousarray(frame, dtype=np.uint8)

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class DummyCamera(Camera):
    """A synthetic camera: each grab returns the next frame of a phase-stepped
    vertical fringe (as if imaging a flat screen), so the full capture and
    reconstruction pipeline runs with no hardware. Not physically meaningful --
    it exists to exercise the plumbing (and the tests)."""

    def __init__(self, width: int = 640, height: int = 512,
                 n_periods: float = 8.0) -> None:
        self.name = "synthetic camera"
        self.width = width
        self.height = height
        self.n_periods = n_periods
        self._n_steps = 8
        self._k = 0
        self._rng = np.random.default_rng(0)

    def set_sequence(self, n_steps: int) -> None:
        self._n_steps = max(1, n_steps)
        self._k = 0

    def open(self) -> None:
        self._k = 0
        log.warning("using the synthetic camera (no real device); frames are simulated")

    def grab(self) -> np.ndarray:
        u = (np.arange(self.width) + 0.5) / self.width
        phase = 2.0 * np.pi * (self._k % self._n_steps) / self._n_steps
        row = 0.5 + 0.5 * np.sin(2.0 * np.pi * self.n_periods * u + phase)
        image = np.broadcast_to(row, (self.height, self.width)).copy()
        noise = self._rng.normal(0.0, 0.01, image.shape)
        self._k += 1
        return np.clip((image + noise) * 255.0, 0, 255).astype(np.uint8)

    def close(self) -> None:
        pass


# -- selection ---------------------------------------------------------------

def has_spinnaker_camera() -> bool:
    """True if the Spinnaker SDK is present *and* a FLIR camera is attached."""
    if not HAS_PYSPIN:
        return False
    system = PySpin.System.GetInstance()
    try:
        cam_list = system.GetCameras()
        count = cam_list.GetSize()
        cam_list.Clear()
        return count > 0
    finally:
        system.ReleaseInstance()


def open_camera(prefer: str | None = None, **kwargs) -> Camera:
    """Construct the camera named by `prefer` (or the MP_CAMERA env var, or
    'auto'): 'spinnaker' | 'opencv' | 'dummy' | 'auto'. 'auto' picks the FLIR
    camera if one is attached, otherwise the synthetic camera (never a webcam,
    to avoid silently grabbing a laptop's built-in camera). The device is not
    opened here -- the capture worker opens it on its own thread."""
    choice = (prefer or os.environ.get("MP_CAMERA") or "auto").strip().lower()
    if choice in ("spinnaker", "flir", "pyspin"):
        return SpinnakerCamera(int(kwargs.get("index", 0)))
    if choice in ("opencv", "usb", "uvc", "webcam"):
        return OpenCVCamera(int(kwargs.get("index", 0)))
    if choice in ("dummy", "synthetic", "sim", "none"):
        return DummyCamera(**{k: v for k, v in kwargs.items() if k in ("width", "height", "n_periods")})
    # auto
    if has_spinnaker_camera():
        return SpinnakerCamera(int(kwargs.get("index", 0)))
    log.warning("no FLIR camera detected; falling back to the synthetic camera "
                "(set MP_CAMERA=opencv to use a USB webcam)")
    return DummyCamera(**{k: v for k, v in kwargs.items() if k in ("width", "height", "n_periods")})
