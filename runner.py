from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
import time
import traceback
from collections import deque

PROJECT_PACKAGE = "projection_simulation"


def _build_command(app_args: list[str]) -> list[str]:
    return [sys.executable, "-m", "projection_simulation", *app_args]


def _run_once(app_args: list[str]) -> int:
    try:
        completed = subprocess.run(_build_command(app_args), check=False)
    except OSError as exc:
        print(f"[runner] Failed to launch app: {exc}", file=sys.stderr, flush=True)
        return 1
    return completed.returncode


def _guard_restart_rate(restart_times: deque[float]) -> None:
    now = time.monotonic()
    restart_times.append(now)
    while restart_times and now - restart_times[0] > 10.0:
        restart_times.popleft()
    if len(restart_times) >= 6:
        print("[runner] Too many rapid restarts, pausing briefly...", flush=True)
        time.sleep(2.0)


def _clear_projection_modules() -> None:
    importlib.invalidate_caches()
    module_names = [
        name
        for name in sys.modules
        if name == PROJECT_PACKAGE or name.startswith(f"{PROJECT_PACKAGE}.")
    ]
    for name in sorted(module_names, key=len, reverse=True):
        sys.modules.pop(name, None)


def _run_debug(app_args: list[str]) -> int:
    restart_times: deque[float] = deque()
    app_module = None
    print("[runner] Debug supervisor started. Press Ctrl+C to stop.", flush=True)

    while True:
        try:
            if app_module is None:
                app_module = importlib.import_module("projection_simulation.app")
            else:
                app_module = importlib.reload(app_module)
            app_main = getattr(app_module, "main", None)
            if not callable(app_main):
                print(
                    "[runner] projection_simulation.app.main is not callable.",
                    file=sys.stderr,
                    flush=True,
                )
                return 1
            result = app_main(app_args, debug_mode=True)
            exit_code = 0 if result is None else int(result)
        except SystemExit as exc:
            try:
                exit_code = int(exc.code) if exc.code is not None else 0
            except (TypeError, ValueError):
                exit_code = 1
            print(
                f"[runner] Debug app requested exit via SystemExit({exc.code!r}).",
                file=sys.stderr if exit_code != 0 else sys.stdout,
                flush=True,
            )
        except KeyboardInterrupt:
            print("\n[runner] Stopping...", flush=True)
            return 130
        except Exception:
            print("[runner] Debug run failed:", file=sys.stderr, flush=True)
            traceback.print_exc()
            return 1

        reload_exit_code = int(getattr(app_module, "RELOAD_EXIT_CODE", 75))
        if exit_code == reload_exit_code:
            try:
                from PySide6.QtWidgets import QApplication

                qt_app = QApplication.instance()
                if qt_app is not None:
                    qt_app.closeAllWindows()
                    qt_app.processEvents()
            except Exception:
                pass
            _guard_restart_rate(restart_times)
            _clear_projection_modules()
            app_module = None
            print("[runner] Reload requested. Restarting...", flush=True)
            continue
        print(
            f"[runner] Debug app exited with code {exit_code}.",
            file=sys.stderr if exit_code != 0 else sys.stdout,
            flush=True,
        )
        return exit_code


def _parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Launch projection_simulation with optional debug mode."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode and press R in the app window to restart the app.",
    )
    args, app_args = parser.parse_known_args()
    return args, app_args


def main() -> int:
    args, app_args = _parse_args()
    if args.debug:
        return _run_debug(app_args)
    return _run_once(app_args)


if __name__ == "__main__":
    raise SystemExit(main())
