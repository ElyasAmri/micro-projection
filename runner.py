from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

WATCHED_SUFFIXES = {".py"}
EXCLUDED_DIRS = {".git", ".archive", "__pycache__", ".idea"}


def _build_command(app_args: list[str]) -> list[str]:
    return [sys.executable, "-m", "projection_simulation", *app_args]


def _launch(app_args: list[str]) -> subprocess.Popen[bytes]:
    command = _build_command(app_args)
    return subprocess.Popen(command)


def _stop_process(process: subprocess.Popen[bytes], timeout: float = 5.0) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def _collect_snapshot(root: Path) -> dict[Path, tuple[int, int]]:
    snapshot: dict[Path, tuple[int, int]] = {}
    for path in root.rglob("*"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if not path.is_file() or path.suffix.lower() not in WATCHED_SUFFIXES:
            continue
        try:
            stat = path.stat()
        except (FileNotFoundError, PermissionError, OSError):
            continue
        snapshot[path] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def _detect_changes(
    previous: dict[Path, tuple[int, int]],
    current: dict[Path, tuple[int, int]],
) -> list[Path]:
    changed_paths: list[Path] = []
    all_paths = set(previous.keys()) | set(current.keys())
    for path in sorted(all_paths):
        if previous.get(path) != current.get(path):
            changed_paths.append(path)
    return changed_paths


def _guard_restart_rate(restart_times: deque[float]) -> None:
    now = time.monotonic()
    restart_times.append(now)
    while restart_times and now - restart_times[0] > 10.0:
        restart_times.popleft()
    if len(restart_times) >= 6:
        print("[runner] Too many rapid restarts, pausing briefly...")
        time.sleep(2.0)


def _run_once(app_args: list[str]) -> int:
    try:
        completed = subprocess.run(_build_command(app_args), check=False)
    except OSError as exc:
        print(f"[runner] Failed to launch app: {exc}", file=sys.stderr)
        return 1
    return completed.returncode


def _run_debug(app_args: list[str], interval: float) -> int:
    root = Path(__file__).resolve().parent
    snapshot = _collect_snapshot(root)
    restart_times: deque[float] = deque()

    try:
        process = _launch(app_args)
    except OSError as exc:
        print(f"[runner] Failed to launch app: {exc}", file=sys.stderr)
        return 1

    print("[runner] Debug mode enabled. Watching for source changes...")

    try:
        while True:
            time.sleep(interval)
            current = _collect_snapshot(root)
            changed = _detect_changes(snapshot, current)
            snapshot = current

            if changed:
                preview = ", ".join(str(p.relative_to(root)) for p in changed[:3])
                suffix = "" if len(changed) <= 3 else ", ..."
                print(f"[runner] Change detected: {preview}{suffix}")
                _guard_restart_rate(restart_times)
                _stop_process(process)
                try:
                    process = _launch(app_args)
                except OSError as exc:
                    print(f"[runner] Failed to relaunch app: {exc}", file=sys.stderr)
                    return 1
                continue

            exit_code = process.poll()
            if exit_code is None:
                continue
            print(f"[runner] App exited with code {exit_code}. Waiting for changes to relaunch...")
            while True:
                time.sleep(interval)
                current = _collect_snapshot(root)
                changed = _detect_changes(snapshot, current)
                snapshot = current
                if not changed:
                    continue
                preview = ", ".join(str(p.relative_to(root)) for p in changed[:3])
                suffix = "" if len(changed) <= 3 else ", ..."
                print(f"[runner] Change detected: {preview}{suffix}")
                _guard_restart_rate(restart_times)
                try:
                    process = _launch(app_args)
                except OSError as exc:
                    print(f"[runner] Failed to relaunch app: {exc}", file=sys.stderr)
                    return 1
                break
    except KeyboardInterrupt:
        print("\n[runner] Stopping...")
        _stop_process(process)
        return 130


def _parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Launch projection_simulation with optional auto-reload debug mode."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Watch source files and restart the app when changes are detected.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.75,
        help="Polling interval in seconds for debug mode. Default: 0.75.",
    )
    args, app_args = parser.parse_known_args()
    if args.interval <= 0:
        parser.error("--interval must be > 0.")
    return args, app_args


def main() -> int:
    args, app_args = _parse_args()
    if args.debug:
        return _run_debug(app_args, args.interval)
    return _run_once(app_args)


if __name__ == "__main__":
    raise SystemExit(main())
