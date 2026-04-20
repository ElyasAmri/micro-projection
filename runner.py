from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
import traceback


def _build_command(app_args: list[str]) -> list[str]:
    return [sys.executable, "-m", "projection_simulation", *app_args]


def _run_once(app_args: list[str]) -> int:
    try:
        completed = subprocess.run(_build_command(app_args), check=False)
    except OSError as exc:
        print(f"[runner] Failed to launch app: {exc}", file=sys.stderr)
        return 1
    return completed.returncode


def _run_debug(app_args: list[str], interval: float) -> int:
    try:
        app_module = importlib.import_module("projection_simulation.app")
        app_main = getattr(app_module, "main", None)
        if not callable(app_main):
            print("[runner] projection_simulation.app.main is not callable.", file=sys.stderr)
            return 1
        result = app_main(app_args, hot_reload_interval=interval)
    except KeyboardInterrupt:
        print("\n[runner] Stopping...")
        return 130
    except Exception:
        print("[runner] Debug launch failed:", file=sys.stderr)
        traceback.print_exc()
        return 1

    if result is None:
        return 0
    return int(result)


def _parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Launch projection_simulation with optional in-place hot-reload debug mode."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Watch source files and hot-reload window code in place.",
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
