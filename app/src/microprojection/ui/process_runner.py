"""Run an external process off the GUI thread and stream its output.

Wraps QProcess (which is asynchronous: it delivers output and completion via
signals on the GUI thread, so nothing blocks). Used to drive the simulation's
Blender capture without freezing the UI.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QProcess, Signal


class ProcessRunner(QObject):
    """Runs one argv at a time, emitting each output line, then exactly one
    terminal signal: `finished(exit_code)` or `failed(message)`."""

    line = Signal(str)
    finished = Signal(int)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._proc: QProcess | None = None
        self._buffer = ""

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.state() != QProcess.NotRunning

    def start(self, argv: list[str], cwd: str) -> None:
        if self.is_running():
            raise RuntimeError("a process is already running")
        self._buffer = ""
        proc = QProcess(self)
        proc.setWorkingDirectory(cwd)
        proc.setProcessChannelMode(QProcess.MergedChannels)  # fold stderr into stdout
        proc.readyReadStandardOutput.connect(self._on_output)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)
        self._proc = proc
        proc.start(argv[0], argv[1:])

    # -- internals ------------------------------------------------------------

    def _on_output(self) -> None:
        if self._proc is None:
            return
        chunk = bytes(self._proc.readAllStandardOutput()).decode("utf-8", "replace")
        self._buffer += chunk
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip("\r")
            if line:
                self.line.emit(line)

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if self._proc is None:  # already resolved via _on_error (failed to start)
            return
        tail = self._buffer.strip()
        self._buffer = ""
        if tail:
            self.line.emit(tail)
        self._proc = None
        if exit_status == QProcess.CrashExit:
            self.failed.emit(f"process crashed (exit {exit_code})")
        else:
            self.finished.emit(int(exit_code))

    def _on_error(self, error: QProcess.ProcessError) -> None:
        # FailedToStart never emits finished(); resolve it here. Other errors
        # (e.g. Crashed) are followed by finished(), which handles them.
        if error == QProcess.FailedToStart:
            self._proc = None
            self.failed.emit("failed to start (is Blender installed? set MP_BLENDER)")
