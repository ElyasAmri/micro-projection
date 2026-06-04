import time

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

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
        self._running = False

    def run(self):
        cap = cv2.VideoCapture(self.device_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            self.error.emit(f"Cannot open OpenCV camera {self.device_index}")
            return

        self._running = True
        frame_count = 0
        fps_timer = time.time()

        while self._running:
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
        self._running = False
        self.wait(3000)


class PySpinCameraThread(QThread):
    """Acquires frames from a FLIR camera via PySpin/Spinnaker."""

    frame_ready = Signal(object)
    error = Signal(str)
    fps_updated = Signal(float)

    def __init__(self, device_index: int = 0, parent=None):
        super().__init__(parent)
        self.device_index = device_index
        self._running = False

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

            # Pixel format
            cam.PixelFormat.SetValue(PySpin.PixelFormat_Mono8)

            # Continuous acquisition
            cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)

            # Auto exposure with a reasonable upper limit
            cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Continuous)
            cam.AutoExposureExposureTimeUpperLimit.SetValue(30000.0)  # 30ms max

            # Framerate: enable manual control, target 30 fps
            cam.AcquisitionFrameRateEnable.SetValue(True)
            cam.AcquisitionFrameRate.SetValue(
                min(30.0, cam.AcquisitionFrameRate.GetMax())
            )

            cam.BeginAcquisition()
        except PySpin.SpinnakerException as e:
            self.error.emit(f"PySpin init failed: {e}")
            del cam
            cam_list.Clear()
            system.ReleaseInstance()
            return

        self._running = True
        frame_count = 0
        fps_timer = time.time()

        while self._running:
            try:
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
                if self._running:
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
        self._running = False
        self.wait(5000)
