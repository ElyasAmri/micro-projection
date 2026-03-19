import time

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

from microprojection.core.datatypes import CaptureFrame


def enumerate_cameras(max_index: int = 8) -> list[dict]:
    """Probe camera indices and return available devices."""
    cameras = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cameras.append({"index": i, "name": f"Camera {i} ({w}x{h})"})
            cap.release()
    return cameras


class CameraThread(QThread):
    """Acquires frames from a USB camera on a dedicated thread."""

    frame_ready = Signal(object)  # CaptureFrame
    error = Signal(str)
    fps_updated = Signal(float)

    def __init__(self, device_index: int = 0, parent=None):
        super().__init__(parent)
        self.device_index = device_index
        self._running = False

    def run(self):
        cap = cv2.VideoCapture(self.device_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            self.error.emit(f"Cannot open camera {self.device_index}")
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
