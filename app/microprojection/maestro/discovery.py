"""Locate a running maestro server to connect to.

maestro advertises every `--serve` listener in `~/.maestro/servers/<port>.json`
with `{port, token, started_at_ms, cwd}`. We read those lockfiles directly (most
recently started first), and also honor the `MAESTRO_SERVER_PORT` /
`MAESTRO_TOKEN` env override, exactly like the Tauri connector's discovery.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Server:
    """A maestro server we can dial: its `/ext` port and matching auth token."""

    port: int
    token: str


def _servers_dir() -> Path:
    # Windows USERPROFILE wins, matching the harness's ~/.maestro resolution.
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    base = Path(home) if home else Path.home()
    return base / ".maestro" / "servers"


def _from_dir(directory: Path) -> list[tuple[int, Server]]:
    if not directory.is_dir():
        return []
    out: list[tuple[int, Server]] = []
    for entry in directory.glob("*.json"):
        try:
            doc = json.loads(entry.read_text())
        except (OSError, ValueError):
            continue
        port = doc.get("port")
        token = doc.get("token")
        if not isinstance(port, int) or not isinstance(token, str):
            continue
        started = doc.get("started_at_ms")
        started = started if isinstance(started, int) else 0
        out.append((started, Server(port=port, token=token)))
    return out


def discover_all() -> list[Server]:
    """All reachable servers, most-recently-started first.

    A stale lockfile or a port now owned by an unrelated server is harmless: the
    register frame carries the token, so a wrong token is rejected and we move on.
    """
    servers: list[Server] = []

    env_port = os.environ.get("MAESTRO_SERVER_PORT")
    env_token = os.environ.get("MAESTRO_TOKEN")
    if env_port and env_token:
        try:
            servers.append(Server(port=int(env_port), token=env_token))
        except ValueError:
            pass

    found = _from_dir(_servers_dir())
    found.sort(key=lambda pair: pair[0], reverse=True)
    servers.extend(server for _, server in found)
    return servers


def discover_one() -> Server | None:
    """The single best server to try, or None when nothing is running."""
    servers = discover_all()
    return servers[0] if servers else None
