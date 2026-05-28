import time
from collections import deque

from PySide6.QtCore import QMutex, QThread, QWaitCondition, Signal

from microprojection.core.datatypes import CaptureFrame, PipelineResult
from microprojection.processing.steps import (
    compute_height,
    compute_roughness,
    extract_phase,
    filter_surface,
    unwrap_phase,
)


class PipelineThread(QThread):
    """Runs the processing pipeline on the most recent frame."""

    result_ready = Signal(object)  # PipelineResult

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._queue: deque[CaptureFrame] = deque(maxlen=1)
        self._condition = QWaitCondition()
        self._mutex = QMutex()
        self._params: dict = {}
        self._params_mutex = QMutex()

    def submit_frame(self, frame: CaptureFrame):
        # Both ends of a QWaitCondition must hold the same mutex.
        self._mutex.lock()
        try:
            self._queue.append(frame)
            self._condition.wakeOne()
        finally:
            self._mutex.unlock()

    def update_params(self, params: dict):
        self._params_mutex.lock()
        self._params = params.copy()
        self._params_mutex.unlock()

    def run(self):
        self._running = True
        while self._running:
            self._mutex.lock()
            try:
                if not self._queue:
                    self._condition.wait(self._mutex, 100)
                frame = self._queue.popleft() if self._queue else None
            finally:
                self._mutex.unlock()

            if frame is None:
                continue

            self._params_mutex.lock()
            params = self._params.copy()
            self._params_mutex.unlock()

            t0 = time.time()
            try:
                phase = extract_phase(
                    frame.image,
                    n_steps=params.get("n_steps", 4),
                    algorithm=params.get("psa_algorithm", "n-step"),
                )
                unwrapped = unwrap_phase(
                    phase, method=params.get("unwrap_method", "temporal")
                )
                height = compute_height(
                    unwrapped, lambda_eq=params.get("lambda_eq", 0.32)
                )
                roughness_map, _ = filter_surface(
                    height,
                    cutoff=params.get("filter_cutoff", 15.0),
                    method=params.get("filter_method", "gaussian"),
                    pixel_pitch_mm=params.get("pixel_pitch_mm", 0.214),
                )
                roughness = compute_roughness(roughness_map)
            except Exception as exc:  # noqa: BLE001
                # A bad parameter (e.g. unimplemented filter method) should not
                # silently kill the worker. Log and skip this frame.
                print(f"[PipelineThread] processing failed: {exc!r}", flush=True)
                continue

            self.result_ready.emit(
                PipelineResult(
                    phase_map=phase,
                    height_map=height,
                    roughness_map=roughness_map,
                    roughness=roughness,
                    processing_time=time.time() - t0,
                )
            )

    def stop(self):
        self._running = False
        self._condition.wakeAll()
        self.wait(3000)
