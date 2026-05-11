import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class FrameProfiler:
    def __init__(self, log_path: Path, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.log_path = log_path
        self._frame_label: str | None = None
        self._frame_started_at = 0.0
        self._frame_index = 0
        self._stats: dict[str, tuple[float, int, float]] = {}

    def begin_frame(self, label: str) -> None:
        if not self.enabled:
            return
        self._frame_label = label
        self._frame_started_at = time.perf_counter()
        self._stats = {}

    def record(self, name: str, duration_s: float) -> None:
        if not self.enabled or self._frame_label is None:
            return
        total, count, max_duration = self._stats.get(name, (0.0, 0, 0.0))
        self._stats[name] = (
            total + duration_s,
            count + 1,
            max(max_duration, duration_s),
        )

    @contextmanager
    def section(self, name: str) -> Iterator[None]:
        if not self.enabled or self._frame_label is None:
            yield
            return
        started_at = time.perf_counter()
        try:
            yield
        finally:
            self.record(name, time.perf_counter() - started_at)

    def end_frame(self) -> None:
        if not self.enabled or self._frame_label is None:
            return
        total_ms = (time.perf_counter() - self._frame_started_at) * 1000.0
        self._frame_index += 1
        sections = sorted(
            self._stats.items(),
            key=lambda item: item[1][0],
            reverse=True,
        )
        section_summary = ", ".join(
            (
                f"{name}={total * 1000.0:.1f}ms/{count}"
                f"(avg={((total / count) * 1000.0):.1f}, max={max_duration * 1000.0:.1f})"
            )
            for name, (total, count, max_duration) in sections[:8]
        )
        self._append(
            f"[perf] {self._frame_label}#{self._frame_index} total={total_ms:.1f}ms"
            + (f" :: {section_summary}" if section_summary else "")
        )
        self._frame_label = None
        self._stats = {}

    def _append(self, message: str) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{message}\n")
