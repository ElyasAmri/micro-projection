import time

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

from microprojection.acquisition.camera_settings import CameraSettings
from microprojection.core.datatypes import CaptureFrame

try:
    import PySpin

    HAS_PYSPIN = True
except ImportError:
    HAS_PYSPIN = False


def enumerate_cameras(max_opencv: int = 8) -> list[dict]:
    """Probe all available cameras (PySpin + OpenCV)."""
    cameras = []

    # PySpin cameras
    if HAS_PYSPIN:
        system = PySpin.System.GetInstance()
        cam_list = system.GetCameras()
        for i in range(cam_list.GetSize()):
            cam = cam_list[i]
            nodemap = cam.GetTLDeviceNodeMap()
            model = PySpin.CStringPtr(nodemap.GetNode("DeviceModelName")).GetValue()
            serial = PySpin.CStringPtr(
                nodemap.GetNode("DeviceSerialNumber")
            ).GetValue()
            del cam
            cameras.append(
                {
                    "backend": "pyspin",
                    "index": i,
                    "name": f"{model} (S/N: {serial})",
                }
            )
        cam_list.Clear()
        system.ReleaseInstance()

    # OpenCV cameras
    for i in range(max_opencv):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cameras.append(
                {
                    "backend": "opencv",
                    "index": i,
                    "name": f"USB Camera {i} ({w}x{h})",
                }
            )
            cap.release()

    return cameras


class OpenCVCameraThread(QThread):
    """Acquires frames from a USB camera via OpenCV."""

    frame_ready = Signal(object)
    error = Signal(str)
    fps_updated = Signal(float)

    def __init__(self, device_index: int = 0, parent=None):
        super().__init__(parent)
        self.device_index = device_index
        # Set once in stop(); never re-set in run(), so a stop requested while
        # the thread is still starting up is not lost (which would orphan it).
        self._stop_requested = False

    def run(self):
        cap = cv2.VideoCapture(self.device_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            self.error.emit(f"Cannot open OpenCV camera {self.device_index}")
            return

        frame_count = 0
        fps_timer = time.time()

        while not self._stop_requested:
            ret, frame = cap.read()
            if not ret:
                self.msleep(1)
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.frame_ready.emit(
                CaptureFrame(image=rgb, timestamp=time.time())
            )

            frame_count += 1
            elapsed = time.time() - fps_timer
            if elapsed >= 1.0:
                self.fps_updated.emit(frame_count / elapsed)
                frame_count = 0
                fps_timer = time.time()

            self.msleep(1)

        cap.release()

    def stop(self):
        self._stop_requested = True
        self.wait(3000)


class PySpinCameraThread(QThread):
    """Acquires frames from a FLIR camera via PySpin/Spinnaker."""

    frame_ready = Signal(object)
    error = Signal(str)
    fps_updated = Signal(float)

    def __init__(self, device_index: int = 0, settings: CameraSettings = None, parent=None):
        super().__init__(parent)
        self.device_index = device_index
        self._settings = settings or CameraSettings()
        # Set once in stop(); never re-set in run(), so a stop requested while
        # the thread is still starting up is not lost (which would orphan it).
        self._stop_requested = False

    def run(self):
        system = PySpin.System.GetInstance()
        cam_list = system.GetCameras()

        if self.device_index >= cam_list.GetSize():
            self.error.emit(f"PySpin camera index {self.device_index} not found")
            cam_list.Clear()
            system.ReleaseInstance()
            return

        cam = cam_list[self.device_index]
        try:
            cam.Init()

            # Self-heal: if a previous session was killed mid-acquisition, the
            # camera is left streaming, which makes PixelFormat read-only
            # ("Node is not writable"). Reboot the device once to clear it.
            if not PySpin.IsWritable(cam.PixelFormat):
                cam.DeviceReset()
                del cam
                cam_list.Clear()
                system.ReleaseInstance()
                cam = None
                for _ in range(20):  # wait for USB re-enumeration (~up to 20s)
                    time.sleep(1.0)
                    system = PySpin.System.GetInstance()
                    cam_list = system.GetCameras()
                    if cam_list.GetSize() > self.device_index:
                        cam = cam_list[self.device_index]
                        cam.Init()
                        break
                    cam_list.Clear()
                    system.ReleaseInstance()
                if cam is None or not PySpin.IsWritable(cam.PixelFormat):
                    self.error.emit(
                        "Camera was locked (prior session not closed cleanly); "
                        "auto-reset failed. Replug the USB cable."
                    )
                    if cam is not None:
                        cam.DeInit()
                        del cam
                    cam_list.Clear()
                    system.ReleaseInstance()
                    return

            # Apply the user's settings (exposure, gain, format, ROI, trigger,
            # etc.) before streaming; structural nodes are only writable here.
            # Imported lazily: this line only runs when PySpin is present.
            from microprojection.acquisition import camera_config
            camera_config.configure(cam, self._settings)

            cam.BeginAcquisition()
        except PySpin.SpinnakerException as e:
            self.error.emit(f"PySpin init failed: {e}")
            del cam
            cam_list.Clear()
            system.ReleaseInstance()
            return

        frame_count = 0
        fps_timer = time.time()

        while not self._stop_requested:
            try:
                # In software-trigger mode the camera only exposes when told to.
                if self._settings.trigger_mode == "Software":
                    try:
                        cam.TriggerSoftware.Execute()
                    except PySpin.SpinnakerException:
                        pass
                image = cam.GetNextImage(1000)  # 1s timeout
                if image.IsIncomplete():
                    image.Release()
                    continue

                arr = image.GetNDArray().copy()
                image.Release()

                self.frame_ready.emit(
                    CaptureFrame(image=arr, timestamp=time.time())
                )

                frame_count += 1
                elapsed = time.time() - fps_timer
                if elapsed >= 1.0:
                    self.fps_updated.emit(frame_count / elapsed)
                    frame_count = 0
                    fps_timer = time.time()

            except PySpin.SpinnakerException:
                if not self._stop_requested:
                    self.msleep(1)

        try:
            cam.EndAcquisition()
            cam.DeInit()
        except PySpin.SpinnakerException:
            pass
        del cam
        cam_list.Clear()
        system.ReleaseInstance()

    def stop(self):
        self._stop_requested = True
        self.wait(5000)
