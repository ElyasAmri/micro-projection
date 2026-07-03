"""Locate a running maestro server to connect to.

maestro advertises every `--serve` listener in `~/.maestro/servers/<port>.json`
with `{port, token, started_at_ms, cwd}`. We read those lockfiles directly and
also honor the `MAESTRO_SERVER_PORT` / `MAESTRO_TOKEN` env override, exactly
like the Tauri connector's discovery.

Lockfiles are ranked, not just sorted by recency: an entry whose recorded
`cwd` contains our own project directory sorts ahead of unrelated ones (most-
recently-started first within each group). Plain recency alone would silently
prefer whichever maestro happened to start last, even when it is serving a
different project -- the same fix ported from the Rust Tauri connector, itself
modeled on Claude Code's IDE-lockfile workspace-folder match.
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


@dataclass(frozen=True)
class _Candidate:
    """One parsed lockfile entry, before ranking."""

    port: int
    token: str
    cwd: str | None
    started_at_ms: int


def _servers_dir() -> Path:
    # Windows USERPROFILE wins, matching the harness's ~/.maestro resolution.
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    base = Path(home) if home else Path.home()
    return base / ".maestro" / "servers"


def _project_dir() -> str:
    """The project directory this app is driving: `MAESTRO_PROJECT_DIR`
    overrides (keeps tests hermetic), otherwise the process cwd. Mirrors the
    Tauri connector's resolution so lockfile matching agrees across clients.
    """
    override = os.environ.get("MAESTRO_PROJECT_DIR")
    if override:
        return override
    return os.getcwd()


def _contains(ancestor: str, path: str) -> bool:
    """True if `path` is `ancestor` itself or nested under it. Boundary-checked
    on the path separator so e.g. `/foo` does not match `/foobar`.
    """
    ancestor = ancestor.rstrip("/\\")
    if not ancestor:
        return False
    return path == ancestor or path.startswith(ancestor + "/") or path.startswith(ancestor + "\\")


def _parse_lockfiles(directory: Path) -> list[_Candidate]:
    if not directory.is_dir():
        return []
    out: list[_Candidate] = []
    for entry in directory.glob("*.json"):
        try:
            doc = json.loads(entry.read_text())
        except (OSError, ValueError):
            continue
        port = doc.get("port")
        token = doc.get("token")
        if not isinstance(port, int) or not isinstance(token, str):
            continue
        cwd = doc.get("cwd")
        cwd = cwd if isinstance(cwd, str) else None
        started = doc.get("started_at_ms")
        started = started if isinstance(started, int) else 0
        out.append(_Candidate(port=port, token=token, cwd=cwd, started_at_ms=started))
    return out


def _ranked_candidates(directory: Path, our_dir: str) -> list[_Candidate]:
    same_project: list[_Candidate] = []
    other: list[_Candidate] = []
    for candidate in _parse_lockfiles(directory):
        if candidate.cwd is not None and _contains(candidate.cwd, our_dir):
            same_project.append(candidate)
        else:
            other.append(candidate)
    same_project.sort(key=lambda c: c.started_at_ms, reverse=True)
    other.sort(key=lambda c: c.started_at_ms, reverse=True)
    return same_project + other


def discover_all() -> list[Server]:
    """All reachable servers, best candidate first: an explicit env pair
    leads, then advertised lockfiles ranked by project match and recency.

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

    ranked = _ranked_candidates(_servers_dir(), _project_dir())
    servers.extend(Server(port=c.port, token=c.token) for c in ranked)
    return servers


def discover_one() -> Server | None:
    """The single best server to try, or None when nothing is running."""
    servers = discover_all()
    return servers[0] if servers else None


def forget(port: int) -> None:
    """Delete the lockfile for `port`, so a dead or unrelated listener is not
    retried on every future discovery pass. Call this only after a dial or
    registration definitively fails (connect error, or an `unauthorized`
    rejection) -- never on an ambiguous disconnect, since a transient hiccup on
    a genuinely live server should not evict a good lockfile. Best-effort: a
    missing or unremovable file is not an error.
    """
    try:
        (_servers_dir() / f"{port}.json").unlink(missing_ok=True)
    except OSError:
        pass
