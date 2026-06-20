"""Tests for the daemon registry (core.runtime.daemon_registry).

subprocess は決して実起動しない: Popen / terminate_pid を monkeypatch する。
"""

from __future__ import annotations

import pytest

import core.runtime.daemon_registry as registry
from core.runtime.daemon_registry import (
    KNOWN_DAEMONS,
    build_command,
    daemon_status,
    get_spec,
    load_enabled,
    set_enabled,
    spawn_daemon,
    stop_daemon,
)
from core.runtime.heartbeat import write_heartbeat


def test_known_daemons_and_get_spec():
    assert set(KNOWN_DAEMONS) == {
        "improvement",
        "content",
        "watchdog",
        "trend",
        "revenue",
        "task",
    }
    assert get_spec("improvement").pid_filename == "daemon.pid"  # 既存レイアウト互換
    assert get_spec("content").pid_filename == "content_daemon.pid"
    assert get_spec("watchdog").pid_filename == "watchdog.pid"
    revenue = get_spec("revenue")
    assert revenue.pid_filename == "revenue_daemon.pid"
    assert revenue.runner_module == "core._revenue_daemon_runner"
    assert revenue.frozen_flag == "--revenue-daemon-run"
    task = get_spec("task")
    assert task.pid_filename == "task_daemon.pid"
    assert task.runner_module == "core._task_daemon_runner"
    assert task.frozen_flag == "--task-daemon-run"
    with pytest.raises(ValueError):
        get_spec("ghost")


def test_cli_daemon_names_match_registry():
    """CLI の argparse choices（DAEMON_NAMES）と KNOWN_DAEMONS のドリフトを機械検出する。

    新デーモン追加時に片方だけ更新すると `daemons start <name>` が choices で弾かれる/
    レジストリに無い名前を受ける、という不整合になる。set 等値で同期を pin する。
    """
    from commands.daemons import DAEMON_NAMES

    assert set(DAEMON_NAMES) == set(KNOWN_DAEMONS)


def test_build_command_non_frozen():
    cmd = build_command(get_spec("content"), ["--interval=600"])
    # daemons launch via the windowless interpreter (pythonw on Windows; == sys.executable elsewhere)
    assert cmd == [
        registry._windowless_python(),
        "-m",
        "core._content_daemon_runner",
        "--interval=600",
    ]


def test_build_command_non_frozen_revenue():
    cmd = build_command(get_spec("revenue"), ["--target=1000"])
    assert cmd == [
        registry._windowless_python(),
        "-m",
        "core._revenue_daemon_runner",
        "--target=1000",
    ]


def test_windowless_python_prefers_sibling_pythonw_on_windows(tmp_path):
    """On Windows, daemons launch via the sibling pythonw.exe when it exists.

    Portable (os_name injected) so the pythonw branch is exercised on Linux CI too —
    the build_command assertions above only pin structure and never reach this branch
    there (where _windowless_python is identically sys.executable).
    """
    py = tmp_path / "python.exe"
    pyw = tmp_path / "pythonw.exe"
    py.write_text("", encoding="utf-8")
    pyw.write_text("", encoding="utf-8")
    assert registry._windowless_python(str(py), os_name="nt") == str(pyw)


def test_windowless_python_falls_back_when_pythonw_missing(tmp_path):
    """No sibling pythonw.exe → return the given interpreter unchanged (no crash)."""
    py = tmp_path / "python.exe"
    py.write_text("", encoding="utf-8")
    assert registry._windowless_python(str(py), os_name="nt") == str(py)


def test_windowless_python_noop_off_windows(tmp_path):
    """Off Windows the gate is skipped — even if a pythonw.exe sibling exists."""
    py = tmp_path / "python"
    pyw = tmp_path / "pythonw.exe"
    py.write_text("", encoding="utf-8")
    pyw.write_text("", encoding="utf-8")
    assert registry._windowless_python(str(py), os_name="posix") == str(py)


def test_build_command_frozen_uses_revenue_flag(monkeypatch):
    # 凍結 exe では -m モジュールではなく frozen_flag のサブコマンドへ分岐する
    monkeypatch.setattr(registry.sys, "frozen", True, raising=False)
    monkeypatch.setattr(registry.sys, "executable", "Pantheon.exe", raising=False)
    cmd = build_command(get_spec("revenue"), ["--target=1000"])
    assert cmd == ["Pantheon.exe", "--revenue-daemon-run", "--target=1000"]


def test_enabled_state_roundtrip(tmp_path):
    assert load_enabled(platform_home=tmp_path) == {}
    set_enabled("content", True, args=["--interval=600"], platform_home=tmp_path)
    state = load_enabled(platform_home=tmp_path)
    assert state["content"] == {"enabled": True, "args": ["--interval=600"]}

    # disable は args を保持したままフラグだけ落とす（再 enable 時に同条件で復元）
    set_enabled("content", False, platform_home=tmp_path)
    state = load_enabled(platform_home=tmp_path)
    assert state["content"]["enabled"] is False
    assert state["content"]["args"] == ["--interval=600"]

    with pytest.raises(ValueError):
        set_enabled("ghost", True, platform_home=tmp_path)


def test_spawn_writes_pid_and_desired_state(tmp_path, monkeypatch):
    captured: dict = {}

    class DummyProc:
        pid = 1234

    def fake_popen(cmd, cwd, stdout, stderr, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["kwargs"] = kwargs
        return DummyProc()

    monkeypatch.setattr(registry.subprocess, "Popen", fake_popen)

    result = spawn_daemon("improvement", args=["--interval=3600"], platform_home=tmp_path)
    assert result["status"] == "started"
    assert result["pid"] == 1234
    assert (tmp_path / "daemon.pid").read_text(encoding="utf-8") == "1234"
    assert captured["cmd"][:3] == [registry._windowless_python(), "-m", "core._daemon_runner"]
    assert captured["cwd"] == registry.PROJECT_ROOT
    # spawn passes the OS-appropriate console-detach kwargs (POSIX setsid /
    # Windows creation flags), not a raw start_new_session that Windows ignores.
    for key, value in registry._detach_popen_kwargs().items():
        assert captured["kwargs"][key] == value
    # Regression: daemons are spawned in UTF-8 mode so print() of non-cp932 chars
    # (em-dash etc.) cannot crash them on Windows where the child stdout defaults
    # to cp932 even when redirected to the (utf-8) log file.
    assert captured["kwargs"]["env"]["PYTHONUTF8"] == "1"
    assert captured["kwargs"]["env"]["PYTHONIOENCODING"] == "utf-8"
    assert load_enabled(platform_home=tmp_path)["improvement"]["enabled"] is True


def test_detach_popen_kwargs_posix_uses_setsid():
    """POSIX detaches via setsid (start_new_session), no Windows creationflags."""
    kw = registry._detach_popen_kwargs("posix")
    assert kw == {"start_new_session": True}


def test_detach_popen_kwargs_windows_uses_creationflags():
    """Windows ignores start_new_session, so we must pass detach creation flags:
    a new process group (isolates console control events) AND a detached console
    (frees the daemon from the launching terminal). Asserted via the documented
    constant values so this runs on any host OS."""
    kw = registry._detach_popen_kwargs("nt")
    assert "start_new_session" not in kw
    flags = kw["creationflags"]
    assert flags & 0x00000200  # CREATE_NEW_PROCESS_GROUP
    assert flags & 0x00000008  # DETACHED_PROCESS
    # exact value so dropping either flag (single-flag swap) is caught precisely.
    assert flags == 0x00000200 | 0x00000008


def test_spawn_already_running(tmp_path, monkeypatch):
    (tmp_path / "daemon.pid").write_text("999", encoding="utf-8")
    monkeypatch.setattr(registry, "is_process_running", lambda pid: True)

    def fail_popen(*a, **k):
        raise AssertionError("must not spawn when already running")

    monkeypatch.setattr(registry.subprocess, "Popen", fail_popen)
    result = spawn_daemon("improvement", platform_home=tmp_path)
    assert result["status"] == "already_running"
    assert result["pid"] == 999


def test_spawn_replaces_dead_pid_file(tmp_path, monkeypatch):
    (tmp_path / "daemon.pid").write_text("999", encoding="utf-8")
    monkeypatch.setattr(registry, "is_process_running", lambda pid: False)

    class DummyProc:
        pid = 1000

    monkeypatch.setattr(registry.subprocess, "Popen", lambda *a, **k: DummyProc())
    result = spawn_daemon("improvement", platform_home=tmp_path)
    assert result["status"] == "started"
    assert (tmp_path / "daemon.pid").read_text(encoding="utf-8") == "1000"


def test_stop_kills_and_disables(tmp_path, monkeypatch):
    (tmp_path / "content_daemon.pid").write_text("555", encoding="utf-8")
    set_enabled("content", True, platform_home=tmp_path)
    killed: dict = {}
    # stop_daemon は単一ソース terminate_pid（Windows-safe）経由で kill する。
    monkeypatch.setattr(registry, "terminate_pid", lambda pid: bool(killed.update(pid=pid)) or True)

    result = stop_daemon("content", platform_home=tmp_path)
    assert result["status"] == "stopped"
    assert killed["pid"] == 555
    assert not (tmp_path / "content_daemon.pid").exists()
    # 明示 stop = watchdog 復元対象から外れる
    assert load_enabled(platform_home=tmp_path)["content"]["enabled"] is False


def test_stop_not_running(tmp_path):
    result = stop_daemon("content", platform_home=tmp_path)
    assert result["status"] == "not_running"
    assert result["pid"] is None


def test_daemon_status_health_matrix(tmp_path, monkeypatch):
    # ① プロセスなし・heartbeat なし → unhealthy / stale
    st = daemon_status("content", platform_home=tmp_path)
    assert st["running"] is False
    assert st["heartbeat_stale"] is True
    assert st["healthy"] is False

    # ② プロセスあり・heartbeat fresh → healthy（pause 中でも heartbeat があれば healthy）
    (tmp_path / "content_daemon.pid").write_text("777", encoding="utf-8")
    monkeypatch.setattr(registry, "is_process_running", lambda pid: True)
    write_heartbeat(
        "content",
        {"status": "paused_rate_limit", "interval_seconds": 600},
        platform_home=tmp_path,
    )
    st = daemon_status("content", platform_home=tmp_path)
    assert st["running"] is True
    assert st["heartbeat_stale"] is False
    assert st["healthy"] is True
    assert st["heartbeat"]["status"] == "paused_rate_limit"
