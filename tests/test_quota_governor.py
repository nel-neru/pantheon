"""Tests for the quota governor (core.runtime.quota_governor)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from core.runtime.quota_governor import (
    PRIORITY_BACKGROUND,
    PRIORITY_CRITICAL,
    PRIORITY_STANDARD,
    QuotaGovernor,
    QuotaRules,
)
from core.runtime.rate_limit import RateLimitInfo
from core.runtime.token_ledger import TokenLedger
from core.runtime.usage_gate import RateLimitGate

NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)
RULES = QuotaRules(window_hours=5, soft_limit_tokens=1000, hard_limit_tokens=2000)


def _ledger_with(tmp_path, total_tokens: int) -> TokenLedger:
    rec = {
        "ts": NOW.isoformat(),
        "input_tokens": total_tokens,
        "output_tokens": 0,
        "model": "sonnet",
    }
    (tmp_path / "claude_calls.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    return TokenLedger(platform_home=tmp_path)


def _governor(tmp_path, total_tokens: int, *, gate: RateLimitGate | None = None) -> QuotaGovernor:
    return QuotaGovernor(
        RULES,
        ledger=_ledger_with(tmp_path, total_tokens),
        gate=gate or RateLimitGate(state_path=tmp_path / "rate_limit_state.json"),
    )


@pytest.fixture(autouse=True)
def _no_kill_switch(monkeypatch):
    monkeypatch.delenv("PANTHEON_QUOTA_GOVERNOR", raising=False)


def test_below_soft_allows_everything(tmp_path):
    gov = _governor(tmp_path, 500)
    for prio in (PRIORITY_BACKGROUND, PRIORITY_STANDARD, PRIORITY_CRITICAL):
        v = gov.allow(prio, now=NOW)
        assert v.allowed is True
        assert v.downgrade is False


def test_soft_exceeded_sheds_background_and_downgrades(tmp_path):
    gov = _governor(tmp_path, 1500)  # soft(1000) <= 1500 < hard(2000)
    assert gov.allow(PRIORITY_BACKGROUND, now=NOW).allowed is False
    std = gov.allow(PRIORITY_STANDARD, now=NOW)
    assert std.allowed is True and std.downgrade is True
    crit = gov.allow(PRIORITY_CRITICAL, now=NOW)
    assert crit.allowed is True and crit.downgrade is True


def test_hard_exceeded_allows_only_critical(tmp_path):
    gov = _governor(tmp_path, 2500)  # >= hard(2000)
    assert gov.allow(PRIORITY_BACKGROUND, now=NOW).allowed is False
    assert gov.allow(PRIORITY_STANDARD, now=NOW).allowed is False
    crit = gov.allow(PRIORITY_CRITICAL, now=NOW)
    assert crit.allowed is True and crit.downgrade is True


def test_rate_limited_denies_all(tmp_path):
    gate = RateLimitGate(state_path=tmp_path / "rate_limit_state.json")
    gate.report(RateLimitInfo(limited=True, reset_at=NOW + timedelta(hours=1)))
    gov = _governor(tmp_path, 0, gate=gate)
    assert gov.allow(PRIORITY_CRITICAL, now=NOW).allowed is False
    assert gov.allow(PRIORITY_STANDARD, now=NOW).reason == "rate_limited"


def test_kill_switch_allows_all(tmp_path, monkeypatch):
    monkeypatch.setenv("PANTHEON_QUOTA_GOVERNOR", "0")
    gov = _governor(tmp_path, 99999)  # 本来 hard 超過でも...
    assert gov.allow(PRIORITY_BACKGROUND, now=NOW).allowed is True


def test_status_reports_level(tmp_path):
    assert _governor(tmp_path, 500).status(now=NOW)["level"] == "ok"
    assert _governor(tmp_path, 1500).status(now=NOW)["level"] == "soft_limit"
    assert _governor(tmp_path, 2500).status(now=NOW)["level"] == "hard_limit"


def test_load_rules_defaults_when_missing(tmp_path):
    from core.runtime.quota_governor import load_rules

    rules = load_rules(tmp_path / "nonexistent.yaml")
    assert rules.window_hours == 5.0
    assert rules.soft_limit_tokens > 0 and rules.hard_limit_tokens > rules.soft_limit_tokens
