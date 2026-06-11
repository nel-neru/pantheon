"""Tests for the daemon watchdog (core.runtime.watchdog).

実プロセスは一切起動しない: registry 関数（load_enabled/daemon_status/
spawn_daemon/stop_daemon）は watchdog モジュール名前空間で monkeypatch する。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import core.runtime.watchdog as wd
from core.runtime.watchdog import (
    ACTION_NONE,
    ACTION_OK,
    ACTION_RESTART,
    ACTION_START,
    WatchdogRunner,
    acquire_single_instance_lock,
    backoff_delay_seconds,
    decide_action,
)

NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)


def test_single_instance_lock_excludes_second_holder(tmp_path):
    """OS 排他ロック: 2 つ目の取得は失敗し、解放後は再取得できる。"""
    first = acquire_single_instance_lock(tmp_path)
    assert first is not None
    assert acquire_single_instance_lock(tmp_path) is None  # 既に保持されている
    first.close()
    third = acquire_single_instance_lock(tmp_path)
    assert third is not None  # 解放後は取得可能（クラッシュ後の再起動を妨げない）
    third.close()


def test_decide_action_branches():
    assert decide_action(enabled=False, pid_alive=False, heartbeat_stale=True) == ACTION_NONE
    assert decide_action(enabled=True, pid_alive=False, heartbeat_stale=True) == ACTION_START
    assert decide_action(enabled=True, pid_alive=True, heartbeat_stale=True) == ACTION_RESTART
    assert decide_action(enabled=True, pid_alive=True, heartbeat_stale=False) == ACTION_OK


def test_backoff_progression():
    assert backoff_delay_seconds(0) == 0.0
    assert backoff_delay_seconds(1) == 30.0
    assert backoff_delay_seconds(2) == 120.0
    assert backoff_delay_seconds(3) == 480.0
    assert backoff_delay_seconds(4) == 1800.0  # 1920 が cap 30m に丸まる
    assert backoff_delay_seconds(10) == 1800.0


def _status(*, running: bool, stale: bool, interval: int = 600) -> Dict[str, Any]:
    return {
        "name": "content",
        "running": running,
        "pid": 111 if running else None,
        "heartbeat_stale": stale,
        "heartbeat": {"interval_seconds": interval},
        "enabled": True,
        "healthy": running and not stale,
        "log_path": "x",
        "heartbeat_age_seconds": None,
        "description": "",
    }


def _wire(monkeypatch, *, enabled_map, status, spawns, stops):
    monkeypatch.setattr(wd, "load_enabled", lambda platform_home=None: enabled_map)
    monkeypatch.setattr(
        wd, "daemon_status", lambda name, now=None, platform_home=None: status(name)
    )
    monkeypatch.setattr(
        wd,
        "spawn_daemon",
        lambda name, args=(), platform_home=None, record_enabled=True: (
            spawns.append((name, list(args), record_enabled)),
            {"status": "started", "pid": 1},
        )[1],
    )
    monkeypatch.setattr(
        wd,
        "stop_daemon",
        lambda name, platform_home=None, record_enabled=True: (
            stops.append((name, record_enabled)),
            {"status": "stopped", "pid": 1},
        )[1],
    )


def test_reconcile_starts_dead_enabled_daemon(monkeypatch):
    spawns: list = []
    stops: list = []
    _wire(
        monkeypatch,
        enabled_map={"content": {"enabled": True, "args": ["--interval=600"]}},
        status=lambda name: _status(running=False, stale=True),
        spawns=spawns,
        stops=stops,
    )
    actions = WatchdogRunner().reconcile_once(now=NOW)
    assert actions == {"content": ACTION_START}
    # 記録済み args で復元し、desired state は書き換えない（record_enabled=False）
    assert spawns == [("content", ["--interval=600"], False)]
    assert stops == []


def test_reconcile_restarts_hung_daemon(monkeypatch):
    spawns: list = []
    stops: list = []
    _wire(
        monkeypatch,
        enabled_map={"content": {"enabled": True, "args": []}},
        status=lambda name: _status(running=True, stale=True),
        spawns=spawns,
        stops=stops,
    )
    actions = WatchdogRunner().reconcile_once(now=NOW)
    assert actions == {"content": ACTION_RESTART}
    assert stops == [("content", False)]
    assert spawns and spawns[0][0] == "content"


def test_reconcile_never_touches_disabled_daemon(monkeypatch):
    spawns: list = []
    stops: list = []
    _wire(
        monkeypatch,
        enabled_map={"content": {"enabled": False, "args": []}},
        status=lambda name: _status(running=False, stale=True),
        spawns=spawns,
        stops=stops,
    )
    actions = WatchdogRunner().reconcile_once(now=NOW)
    assert actions == {"content": ACTION_NONE}
    assert spawns == [] and stops == []


def test_reconcile_skips_watchdog_itself(monkeypatch):
    spawns: list = []
    stops: list = []
    _wire(
        monkeypatch,
        enabled_map={"watchdog": {"enabled": True, "args": []}},
        status=lambda name: _status(running=False, stale=True),
        spawns=spawns,
        stops=stops,
    )
    actions = WatchdogRunner().reconcile_once(now=NOW)
    assert actions == {}
    assert spawns == [] and stops == []


def test_backoff_defers_repeated_starts(monkeypatch):
    spawns: list = []
    stops: list = []
    _wire(
        monkeypatch,
        enabled_map={"content": {"enabled": True, "args": []}},
        status=lambda name: _status(running=False, stale=True),
        spawns=spawns,
        stops=stops,
    )
    runner = WatchdogRunner()
    assert runner.reconcile_once(now=NOW)["content"] == ACTION_START
    # 30 秒の backoff 内 → 起動を見送る
    assert runner.reconcile_once(now=NOW + timedelta(seconds=10))["content"] == "start_deferred"
    # backoff 経過後 → 再試行
    assert runner.reconcile_once(now=NOW + timedelta(seconds=40))["content"] == ACTION_START
    assert len(spawns) == 2


def test_grace_after_spawn_prevents_false_restart(monkeypatch):
    """spawn 直後（初回 heartbeat 前）の stale を「ハング」と誤判定しない。"""
    spawns: list = []
    stops: list = []
    state = {"running": False}

    def status(name):
        return _status(running=state["running"], stale=True, interval=600)

    _wire(
        monkeypatch,
        enabled_map={"content": {"enabled": True, "args": []}},
        status=status,
        spawns=spawns,
        stops=stops,
    )
    runner = WatchdogRunner()
    assert runner.reconcile_once(now=NOW)["content"] == ACTION_START

    # spawn 後にプロセスは生きたが heartbeat はまだ → grace 内なので restart しない
    state["running"] = True
    actions = runner.reconcile_once(now=NOW + timedelta(seconds=90))
    assert actions["content"] == ACTION_OK
    assert stops == []
    # grace 中の「見かけ上の健康」では backoff カウンタを保持（クラッシュループ抑制）
    assert runner._guards["content"].attempts == 1

    # grace（threshold=1800s）を超えてもまだ stale → 本物のハングとして restart
    actions = runner.reconcile_once(now=NOW + timedelta(seconds=1900))
    assert actions["content"] == ACTION_RESTART


def test_ok_resets_backoff(monkeypatch):
    spawns: list = []
    stops: list = []
    state = {"running": False, "stale": True}
    _wire(
        monkeypatch,
        enabled_map={"content": {"enabled": True, "args": []}},
        status=lambda name: _status(running=state["running"], stale=state["stale"]),
        spawns=spawns,
        stops=stops,
    )
    runner = WatchdogRunner()
    runner.reconcile_once(now=NOW)
    assert runner._guards["content"].attempts == 1

    # grace を超えた時点で健康 → backoff リセット
    state.update(running=True, stale=False)
    actions = runner.reconcile_once(now=NOW + timedelta(seconds=1900))
    assert actions["content"] == ACTION_OK
    assert runner._guards["content"].attempts == 0
