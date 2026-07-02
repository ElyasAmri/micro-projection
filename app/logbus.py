"""Application logging.

App code logs through the stdlib `logging` module under the "mp" namespace
(the maestro connector logs under "mp.maestro"); the console is just a handler,
so every record -- app or maestro -- renders there and, in a terminal, on
stderr. `configure()` wires the handlers once at startup.

A SUCCESS level (between INFO and WARNING) carries the green "done" messages;
use `success(logger, msg)` for it.
"""
from __future__ import annotations

import logging

ROOT = "mp"

SUCCESS = 25
logging.addLevelName(SUCCESS, "SUCCESS")


def get_logger(name: str | None = None) -> logging.Logger:
    """A logger under the app's namespace (e.g. get_logger("ui") -> "mp.ui")."""
    return logging.getLogger(ROOT if name is None else f"{ROOT}.{name}")


def success(logger: logging.Logger, message: str, *args) -> None:
    """Log at the SUCCESS level (rendered green in the console)."""
    if logger.isEnabledFor(SUCCESS):
        logger.log(SUCCESS, message, *args)


def configure(console_handler: logging.Handler, level: int = logging.INFO) -> None:
    """Route the app namespace to the console (and stderr). Idempotent: replaces
    any previously installed handlers on the "mp" logger."""
    logger = logging.getLogger(ROOT)
    logger.handlers.clear()
    logger.setLevel(level)
    logger.addHandler(console_handler)

    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    logger.addHandler(stream)

    logger.propagate = False  # don't double-log via the root logger
