"""Tests for the embedded terminal backend (web/terminal.py + REST/WS endpoints)."""

from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import web.server as server
from web.terminal import TerminalManager, is_loopback_host

client = TestClient(server.app)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="PTY は Unix のみ")


def test_is_loopback_host():
    assert is_loopback_host("127.0.0.1") is True
    assert is_loopback_host("::1") is True
    assert is_loopback_host(None) is True
    assert is_loopback_host("testclient") is True
    assert is_loopback_host("10.0.0.5") is False
    assert is_loopback_host("example.com") is False


def test_resolve_command_variants(tmp_path):
    mgr = TerminalManager(default_cwd=tmp_path)
    # 既定: シェル
    shell_cmd = mgr._resolve_command(None, None, None)
    assert shell_cmd and isinstance(shell_cmd, list)
    # command 文字列は shlex 分割
    assert mgr._resolve_command("echo hello world", None, None) == ["echo", "hello", "world"]
    # cli_tool は registry から解決
    assert mgr._resolve_command(None, "claude", None) == ["claude"]
    assert mgr._resolve_command(None, "claude", {"cli_commands": {"claude": "claude-x"}}) == ["claude-x"]
    with pytest.raises(ValueError):
        mgr._resolve_command(None, "nonexistent-tool", None)


def test_create_rejects_bad_cwd(tmp_path):
    mgr = TerminalManager(default_cwd=tmp_path)
    with pytest.raises(ValueError):
        mgr.create(cwd=str(tmp_path / "does-not-exist"))


def test_create_and_kill_session(tmp_path):
    mgr = TerminalManager(default_cwd=tmp_path)
    try:
        session = mgr.create(name="t", command="sleep 30")
        meta = session.meta()
        assert meta["status"] == "running"
        assert meta["command"] == ["sleep", "30"]
        assert meta["name"] == "t"
        assert any(s["id"] == session.id for s in mgr.list())
        assert mgr.kill(session.id) is True
        assert mgr.kill(session.id) is False  # already removed
    finally:
        mgr.shutdown()


def test_git_branch_detected(tmp_path):
    git = pytest.importorskip("git")
    repo = git.Repo.init(tmp_path)
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "t")
        cw.set_value("user", "email", "t@e.com")
    repo.index.add(["x.txt"])
    repo.index.commit("init")

    mgr = TerminalManager(default_cwd=tmp_path)
    try:
        session = mgr.create(command="sleep 30")
        branch = session.meta()["git_branch"]
        assert branch in {"main", "master"}
    finally:
        mgr.shutdown()


async def test_pty_produces_output(tmp_path):
    mgr = TerminalManager(default_cwd=tmp_path)
    loop = asyncio.get_running_loop()
    try:
        session = mgr.create(command="/bin/sh -c 'echo TERMOK'")
        session.start_reader(loop)
        for _ in range(60):
            await asyncio.sleep(0.05)
            if b"TERMOK" in bytes(session.scrollback):
                break
        assert b"TERMOK" in bytes(session.scrollback)
    finally:
        mgr.shutdown()


def test_require_localhost_blocks_remote():
    remote = SimpleNamespace(client=SimpleNamespace(host="10.0.0.9"))
    with pytest.raises(server.HTTPException) as exc:
        server._require_localhost(remote)  # type: ignore[arg-type]
    assert exc.value.status_code == 403


def test_terminal_rest_create_list_kill():
    created = client.post("/api/terminal/sessions", json={"name": "rest", "command": "sleep 30"})
    assert created.status_code == 200, created.text
    session_id = created.json()["id"]
    try:
        listed = client.get("/api/terminal/sessions")
        assert listed.status_code == 200
        assert any(s["id"] == session_id for s in listed.json()["sessions"])
    finally:
        killed = client.delete(f"/api/terminal/sessions/{session_id}")
        assert killed.status_code == 200

    assert client.delete(f"/api/terminal/sessions/{session_id}").status_code == 404


def test_terminal_websocket_echo():
    created = client.post("/api/terminal/sessions", json={"command": "/bin/sh -c 'echo WSOK; sleep 30'"})
    session_id = created.json()["id"]
    try:
        with client.websocket_connect(f"/ws/terminal/{session_id}") as ws:
            received = b""
            for _ in range(40):
                message = ws.receive()
                if "bytes" in message and message["bytes"]:
                    received += message["bytes"]
                    if b"WSOK" in received:
                        break
                elif message.get("text"):
                    break
            assert b"WSOK" in received
    finally:
        client.delete(f"/api/terminal/sessions/{session_id}")


def test_terminal_websocket_input_and_resize_controls():
    """F4: resize/input 制御メッセージが PTY に届き、不正入力でも落ちない。"""
    created = client.post("/api/terminal/sessions", json={"command": "cat"})
    session_id = created.json()["id"]
    try:
        with client.websocket_connect(f"/ws/terminal/{session_id}") as ws:
            ws.send_text(json.dumps({"type": "resize", "rows": 30, "cols": 100}))
            ws.send_text("{not valid json")  # 不正制御 → 生入力として扱い落ちない
            ws.send_text(json.dumps({"type": "input", "data": "PINGPONG\n"}))
            received = b""
            for _ in range(60):
                message = ws.receive()
                if message.get("bytes"):
                    received += message["bytes"]
                    if b"PINGPONG" in received:
                        break
                elif message.get("text"):
                    continue
            assert b"PINGPONG" in received
    finally:
        client.delete(f"/api/terminal/sessions/{session_id}")


# --------------------------------------------------------------------------- #
# C11: セッションのリネーム
# --------------------------------------------------------------------------- #


def test_rename_session(tmp_path):
    mgr = TerminalManager(default_cwd=tmp_path)
    session = mgr.create(name="old", command="sleep 30")
    try:
        assert mgr.rename(session.id, "new-name") is True
        assert session.meta()["name"] == "new-name"
        # 空文字は無視（変更されない）
        mgr.rename(session.id, "   ")
        assert session.meta()["name"] == "new-name"
        # 存在しない ID は False
        assert mgr.rename("nonexistent", "x") is False
    finally:
        mgr.kill(session.id)


def test_rename_session_rest(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "s.json")
    created = client.post("/api/terminal/sessions", json={"command": "sleep 30", "name": "a"})
    session_id = created.json()["id"]
    try:
        resp = client.patch(f"/api/terminal/sessions/{session_id}", json={"name": "renamed"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "renamed"
        # 不在 ID は 404
        assert client.patch("/api/terminal/sessions/missing", json={"name": "x"}).status_code == 404
    finally:
        client.delete(f"/api/terminal/sessions/{session_id}")


# --------------------------------------------------------------------------- #
# C1: アイドルセッションの GC
# --------------------------------------------------------------------------- #


def test_gc_reaps_exited_sessions(tmp_path):
    import time

    mgr = TerminalManager(default_cwd=tmp_path)
    session = mgr.create(command="sleep 30")
    # exited かつ最終活動が古い → 回収される
    session.status = "exited"
    session.last_activity = time.monotonic() - 1000
    assert mgr.gc(exited_ttl=300) == 1
    assert mgr.get(session.id) is None


def test_gc_reaps_idle_running_without_subscribers(tmp_path):
    import time

    mgr = TerminalManager(default_cwd=tmp_path)
    session = mgr.create(command="sleep 30")
    try:
        session.last_activity = time.monotonic() - 100
        assert mgr.gc(idle_ttl=10) == 1  # 購読者ゼロ + アイドル → kill+削除
        assert mgr.get(session.id) is None
    finally:
        mgr.kill(session.id)


def test_gc_keeps_sessions_with_subscribers(tmp_path):
    import time

    mgr = TerminalManager(default_cwd=tmp_path)
    session = mgr.create(command="sleep 30")
    try:
        session.subscribe()
        session.last_activity = time.monotonic() - 100
        assert mgr.gc(idle_ttl=10) == 0  # 購読者あり → 保持
        assert mgr.get(session.id) is not None
    finally:
        mgr.kill(session.id)


def test_gc_keeps_recently_active(tmp_path):
    mgr = TerminalManager(default_cwd=tmp_path)
    session = mgr.create(command="sleep 30")
    try:
        assert mgr.gc(idle_ttl=3600) == 0  # 直近に作成 → 保持
        assert mgr.get(session.id) is not None
    finally:
        mgr.kill(session.id)


# --------------------------------------------------------------------------- #
# C5: Windows 未対応の明示
# --------------------------------------------------------------------------- #


def test_create_raises_clear_message_when_pty_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr("web.terminal._PTY_AVAILABLE", False)
    mgr = TerminalManager(default_cwd=tmp_path)
    with pytest.raises(ValueError, match="Windows"):
        mgr.create(command="sleep 30")
