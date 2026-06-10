"""Tests for the cross-process rate-limit gate (core.runtime.usage_gate)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from core.runtime.rate_limit import RateLimitInfo
from core.runtime.usage_gate import RateLimitGate


def _gate(tmp_path) -> RateLimitGate:
    return RateLimitGate(state_path=tmp_path / "rate_limit_state.json")


def test_report_and_current_roundtrip(tmp_path):
    gate = _gate(tmp_path)
    reset = datetime.now(timezone.utc) + timedelta(minutes=30)
    gate.report(
        RateLimitInfo(limited=True, reset_at=reset, scope="weekly", message="usage limit reached")
    )

    info = gate.current()
    assert info is not None and info.limited
    assert info.reset_at == reset
    assert info.scope == "weekly"
    assert info.message == "usage limit reached"
    assert gate.is_limited()
    assert 0.0 < gate.seconds_until_clear() <= 30 * 60


def test_current_auto_clears_after_reset(tmp_path):
    gate = _gate(tmp_path)
    reset = datetime.now(timezone.utc) - timedelta(seconds=1)
    gate.report(RateLimitInfo(limited=True, reset_at=reset))

    # 窓が開いた → current() が自動 clear して None（「解除されたら再開」の起点）。
    assert gate.current() is None
    assert not gate.state_path.exists()
    assert gate.is_limited() is False
    assert gate.seconds_until_clear() == 0.0


def test_report_not_limited_is_noop(tmp_path):
    gate = _gate(tmp_path)
    gate.report(RateLimitInfo(limited=False))
    assert not gate.state_path.exists()
    assert gate.current() is None


def test_clear_is_idempotent(tmp_path):
    gate = _gate(tmp_path)
    gate.clear()  # 何も無い状態でも安全
    gate.report(
        RateLimitInfo(limited=True, reset_at=datetime.now(timezone.utc) + timedelta(hours=1))
    )
    gate.clear()
    assert gate.current() is None


def test_corrupt_state_file_returns_none_and_clears(tmp_path):
    gate = _gate(tmp_path)
    gate.state_path.parent.mkdir(parents=True, exist_ok=True)
    gate.state_path.write_text("{not json", encoding="utf-8")
    assert gate.current() is None
    assert not gate.state_path.exists()


def test_missing_reset_at_stays_limited(tmp_path):
    gate = _gate(tmp_path)
    gate.report(RateLimitInfo(limited=True, reset_at=None, message="429"))
    info = gate.current()
    assert info is not None and info.limited
    assert info.reset_at is None
    # reset 不明時は RateLimitInfo の既定バックオフが効く
    assert gate.seconds_until_clear() > 0.0


def test_missing_reset_at_expires_after_default_backoff(tmp_path):
    """reset 不明レコードで永久ブロックしない: detected_at + 既定バックオフで自動 clear。"""
    gate = _gate(tmp_path)
    gate.report(RateLimitInfo(limited=True, reset_at=None, message="429"))
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    assert gate.current(now=future) is None
    assert not gate.state_path.exists()


def test_missing_reset_and_detected_at_clears_immediately(tmp_path):
    gate = _gate(tmp_path)
    gate.state_path.parent.mkdir(parents=True, exist_ok=True)
    gate.state_path.write_text(
        json.dumps({"limited": True, "reset_at": None, "detected_at": "not-a-date"}),
        encoding="utf-8",
    )
    assert gate.current() is None
    assert not gate.state_path.exists()


def test_default_path_uses_platform_home(tmp_path, monkeypatch):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    gate = RateLimitGate()
    reset = datetime.now(timezone.utc) + timedelta(hours=1)
    gate.report(RateLimitInfo(limited=True, reset_at=reset))

    state_file = tmp_path / "rate_limit_state.json"
    assert state_file.exists()
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["limited"] is True
    assert data["reset_at"] == reset.isoformat()
