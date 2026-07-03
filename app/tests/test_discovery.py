"""Server discovery: lockfile parsing, project-cwd ranking, and the env override."""
from __future__ import annotations

import json

from maestro import discovery


def _write_lockfile(servers_dir, port, token, started_at_ms, cwd="/x"):
    servers_dir.mkdir(parents=True, exist_ok=True)
    doc = {"port": port, "token": token, "started_at_ms": started_at_ms}
    if cwd is not None:
        doc["cwd"] = cwd
    (servers_dir / f"{port}.json").write_text(json.dumps(doc))


def test_reads_lockfiles_newest_first(tmp_path, monkeypatch):
    monkeypatch.delenv("MAESTRO_SERVER_PORT", raising=False)
    monkeypatch.delenv("MAESTRO_TOKEN", raising=False)
    monkeypatch.delenv("MAESTRO_PROJECT_DIR", raising=False)
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


def test_prefers_matching_project_over_recency(tmp_path, monkeypatch):
    monkeypatch.delenv("MAESTRO_SERVER_PORT", raising=False)
    monkeypatch.delenv("MAESTRO_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("MAESTRO_PROJECT_DIR", "/work/proj/subdir")
    servers = tmp_path / ".maestro" / "servers"
    # Started first, but its cwd is our project -- should still win.
    _write_lockfile(servers, 1111, "ours", 100, cwd="/work/proj")
    # Started more recently, unrelated project -- must not shadow it.
    _write_lockfile(servers, 2222, "theirs", 200, cwd="/work/other")

    found = discovery.discover_all()
    assert [s.port for s in found] == [1111, 2222]
    assert discovery.discover_one().port == 1111


def test_lockfile_without_cwd_falls_back_to_recency(tmp_path, monkeypatch):
    monkeypatch.delenv("MAESTRO_SERVER_PORT", raising=False)
    monkeypatch.delenv("MAESTRO_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("MAESTRO_PROJECT_DIR", "/work/proj")
    servers = tmp_path / ".maestro" / "servers"
    _write_lockfile(servers, 1111, "old", 100, cwd=None)
    _write_lockfile(servers, 2222, "new", 200, cwd=None)

    found = discovery.discover_all()
    assert [s.port for s in found] == [2222, 1111]


def test_forget_removes_lockfile(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    servers = tmp_path / ".maestro" / "servers"
    _write_lockfile(servers, 5555, "tok", 1)
    assert (servers / "5555.json").exists()

    discovery.forget(5555)
    assert not (servers / "5555.json").exists()

    # Forgetting an already-gone (or never-existing) lockfile is a no-op.
    discovery.forget(5555)
    discovery.forget(9999)
