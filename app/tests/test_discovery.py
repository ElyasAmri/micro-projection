"""Server discovery: lockfile parsing and the env override."""
from __future__ import annotations

import json

from microprojection.maestro import discovery


def _write_lockfile(servers_dir, port, token, started_at_ms):
    servers_dir.mkdir(parents=True, exist_ok=True)
    (servers_dir / f"{port}.json").write_text(
        json.dumps(
            {"port": port, "token": token, "started_at_ms": started_at_ms, "cwd": "/x"}
        )
    )


def test_reads_lockfiles_newest_first(tmp_path, monkeypatch):
    monkeypatch.delenv("MAESTRO_SERVER_PORT", raising=False)
    monkeypatch.delenv("MAESTRO_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    servers = tmp_path / ".maestro" / "servers"
    _write_lockfile(servers, 8001, "tok-old", 1000)
    _write_lockfile(servers, 8002, "tok-new", 2000)

    found = discovery.discover_all()
    assert [(s.port, s.token) for s in found] == [(8002, "tok-new"), (8001, "tok-old")]
    assert discovery.discover_one().port == 8002


def test_skips_incomplete_lockfiles(tmp_path, monkeypatch):
    monkeypatch.delenv("MAESTRO_SERVER_PORT", raising=False)
    monkeypatch.delenv("MAESTRO_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    servers = tmp_path / ".maestro" / "servers"
    servers.mkdir(parents=True)
    (servers / "bad.json").write_text("{ not json")
    (servers / "9000.json").write_text(json.dumps({"port": 9000}))  # no token

    assert discovery.discover_all() == []


def test_env_override_takes_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("MAESTRO_SERVER_PORT", "7777")
    monkeypatch.setenv("MAESTRO_TOKEN", "env-tok")

    first = discovery.discover_one()
    assert first is not None
    assert (first.port, first.token) == (7777, "env-tok")
