"""Rate-limit pause → auto-resume behaviour of both daemon schedulers.

「レート制限を検知してもプロセスは生き続け、reset 時刻に達したら自動で再開する」
（= 制限解除されたら再開を無限に繰り返す）の中核テスト。実時間 sleep には依存せず、
過去の reset 時刻・fake sleep・fake cycle で決定論的に検証する。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from core.content.content_scheduler import (
    STATUS_PAUSED_RATE_LIMIT,
    STATUS_RUNNING,
    ContentScheduler,
)
from core.runtime.claude_code import ClaudeRateLimitedError
from core.runtime.rate_limit import RateLimitInfo
from core.runtime.usage_gate import RateLimitGate
from core.scheduler import AutonomousScheduler


@pytest.fixture()
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    return tmp_path


def _past_iso(seconds: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _future_iso(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


# ---------------------------------------------------------------- Content daemon
async def test_content_pause_resumes_when_reset_passed(isolated_home):
    sched = ContentScheduler(platform_home=isolated_home, interval_seconds=1)
    sched._running = True
    sched._rate_limited = True
    sched._retry_at = _past_iso()

    await sched._pause_until_reset()

    assert sched._rate_limited is False
    assert sched._retry_at is None
    state = json.loads((isolated_home / "content_scheduler_state.json").read_text(encoding="utf-8"))
    assert state["status"] == STATUS_RUNNING
    assert state["running"] is True


async def test_content_pause_writes_paused_state_while_waiting(isolated_home, monkeypatch):
    sched = ContentScheduler(platform_home=isolated_home, interval_seconds=1)
    sched._running = True
    sched._rate_limited = True
    sched._retry_at = _future_iso()

    orig_sleep = asyncio.sleep
    seen_statuses: list[str] = []

    async def fake_sleep(seconds: float) -> None:
        state = json.loads(
            (isolated_home / "content_scheduler_state.json").read_text(encoding="utf-8")
        )
        seen_statuses.append(state["status"])
        sched.stop()
        await orig_sleep(0)

    monkeypatch.setattr("core.content.content_scheduler.asyncio.sleep", fake_sleep)
    await asyncio.wait_for(sched._pause_until_reset(), timeout=5)

    assert seen_statuses == [STATUS_PAUSED_RATE_LIMIT]
    # stop() で中断されたので resume 処理（rate_limited クリア）は走らない
    assert sched._rate_limited is True


async def test_content_loop_auto_resumes_and_retries(isolated_home, monkeypatch):
    sched = ContentScheduler(platform_home=isolated_home, interval_seconds=1, run_pdca=False)
    calls: list[int] = []

    async def fake_run_cycle() -> bool:
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            sched._rate_limited = True
            sched._retry_at = _past_iso()
            return True  # レート制限検知 → pause（reset は過去なので即 resume）
        sched.stop()
        return False

    monkeypatch.setattr(sched, "run_cycle", fake_run_cycle)
    await asyncio.wait_for(sched.start(), timeout=10)

    assert len(calls) >= 2  # 制限後に自動 resume して同一ループ内で再実行された
    assert sched._rate_limited is False


async def test_content_loop_pauses_from_cross_process_gate(isolated_home, monkeypatch):
    """別プロセスが gate に書いた制限でも、cycle を回さず先回りして pause する。"""
    RateLimitGate().report(
        RateLimitInfo(
            limited=True,
            reset_at=datetime.now(timezone.utc) + timedelta(hours=1),
            message="usage limit",
        )
    )
    sched = ContentScheduler(platform_home=isolated_home, interval_seconds=1, run_pdca=False)

    async def fail_cycle() -> bool:
        raise AssertionError("run_cycle must not run while the gate is limited")

    monkeypatch.setattr(sched, "run_cycle", fail_cycle)

    orig_sleep = asyncio.sleep
    seen_statuses: list[str] = []

    async def fake_sleep(seconds: float) -> None:
        state = json.loads(
            (isolated_home / "content_scheduler_state.json").read_text(encoding="utf-8")
        )
        seen_statuses.append(state["status"])
        sched.stop()
        await orig_sleep(0)

    monkeypatch.setattr("core.content.content_scheduler.asyncio.sleep", fake_sleep)
    await asyncio.wait_for(sched.start(), timeout=5)

    assert STATUS_PAUSED_RATE_LIMIT in seen_statuses


async def test_content_run_cycle_keeps_running_state_on_rate_limit(isolated_home, monkeypatch):
    """run_cycle がレート制限を返しても running は落とさない（pause して自動 resume するため）。"""
    sched = ContentScheduler(platform_home=isolated_home, interval_seconds=1, run_pdca=False)
    sched._running = True

    class _Job:
        job_id = "j1"

    monkeypatch.setattr(sched._store, "due_jobs", lambda: [_Job()])

    async def fake_run_content_job(job, psm):
        return {"status": "rate_limited", "retry_at": _future_iso(), "detail": "usage limit"}

    monkeypatch.setattr("core.content.content_scheduler.run_content_job", fake_run_content_job)

    limited = await sched.run_cycle()
    assert limited is True
    state = json.loads((isolated_home / "content_scheduler_state.json").read_text(encoding="utf-8"))
    assert state["running"] is True
    assert state["status"] == STATUS_PAUSED_RATE_LIMIT
    assert state["retry_at"] == sched._retry_at


# ------------------------------------------------------------ Improvement daemon
async def test_autonomous_loop_pauses_on_rate_limit_then_resumes(isolated_home, monkeypatch):
    sched = AutonomousScheduler(platform_home=isolated_home, interval_seconds=1)
    calls: list[int] = []
    past_info = RateLimitInfo(
        limited=True, reset_at=datetime.now(timezone.utc) - timedelta(seconds=1)
    )

    async def fake_cycle():
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            raise ClaudeRateLimitedError("claude usage limit reached", past_info)
        sched.stop()
        return {}

    monkeypatch.setattr(sched, "_run_cycle", fake_cycle)
    await asyncio.wait_for(sched.start(), timeout=10)

    assert len(calls) >= 2  # 例外で止まらず、reset 後に自動 resume して再実行された


async def test_autonomous_loop_blocks_cycle_while_gate_limited(isolated_home, monkeypatch):
    RateLimitGate().report(
        RateLimitInfo(
            limited=True,
            reset_at=datetime.now(timezone.utc) + timedelta(hours=1),
            message="usage limit",
        )
    )
    sched = AutonomousScheduler(platform_home=isolated_home, interval_seconds=1)

    async def fail_cycle():
        raise AssertionError("_run_cycle must not run while the gate is limited")

    monkeypatch.setattr(sched, "_run_cycle", fail_cycle)

    orig_sleep = asyncio.sleep
    paused = []

    async def fake_sleep(seconds: float) -> None:
        paused.append(seconds)
        sched.stop()
        await orig_sleep(0)

    monkeypatch.setattr("core.scheduler.asyncio.sleep", fake_sleep)
    await asyncio.wait_for(sched.start(), timeout=5)

    assert paused  # pause ループに入った（cycle は一度も走っていない）
