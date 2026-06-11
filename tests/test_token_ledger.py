"""Tests for the token ledger (core.runtime.token_ledger)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from core.runtime.token_ledger import TokenLedger


def _write_calls(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _rec(ts, **kw):
    base = {"ts": ts.isoformat(), "model": "sonnet"}
    base.update(kw)
    return base


def test_empty_when_no_log(tmp_path):
    usage = TokenLedger(platform_home=tmp_path).window_usage(5)
    assert usage.calls == 0
    assert usage.total_tokens == 0


def test_window_filters_old_records(tmp_path):
    now = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)
    _write_calls(
        tmp_path / "claude_calls.jsonl",
        [
            _rec(now - timedelta(hours=1), input_tokens=1000, output_tokens=200),  # 窓内
            _rec(now - timedelta(hours=6), input_tokens=9999, output_tokens=9999),  # 窓外(5h)
        ],
    )
    usage = TokenLedger(platform_home=tmp_path).window_usage(5, now=now)
    assert usage.calls == 1
    assert usage.input_tokens == 1000
    assert usage.output_tokens == 200
    assert usage.total_tokens == 1200
    assert usage.measured_calls == 1


def test_char_estimate_fallback_for_old_cli(tmp_path):
    now = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)
    _write_calls(
        tmp_path / "claude_calls.jsonl",
        [
            # 実測トークン無し → prompt_chars+system_chars / 4 + 既定 output 概算
            _rec(now - timedelta(minutes=5), prompt_chars=400, system_chars=400),
        ],
    )
    usage = TokenLedger(platform_home=tmp_path).window_usage(5, now=now)
    assert usage.estimated_calls == 1
    assert usage.input_tokens == 200  # (400+400)/4
    assert usage.output_tokens == 500  # 既定概算


def test_cost_and_cache_aggregated(tmp_path):
    now = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)
    _write_calls(
        tmp_path / "claude_calls.jsonl",
        [
            _rec(
                now,
                input_tokens=100,
                output_tokens=50,
                cache_read_tokens=900,
                total_cost_usd=0.01,
            ),
            _rec(now, input_tokens=200, output_tokens=80, total_cost_usd=0.02),
        ],
    )
    usage = TokenLedger(platform_home=tmp_path).window_usage(5, now=now)
    assert usage.cache_read_tokens == 900
    assert round(usage.total_cost_usd, 4) == 0.03
    assert usage.total_tokens == 430


def test_corrupt_lines_skipped(tmp_path):
    now = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)
    path = tmp_path / "claude_calls.jsonl"
    path.write_text(
        "\n".join(
            [
                "{broken json",
                json.dumps(_rec(now, input_tokens=10, output_tokens=5)),
                "",
                "not json either",
            ]
        ),
        encoding="utf-8",
    )
    usage = TokenLedger(platform_home=tmp_path).window_usage(5, now=now)
    assert usage.calls == 1
    assert usage.total_tokens == 15


def test_summary_has_both_windows(tmp_path):
    now = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)
    _write_calls(
        tmp_path / "claude_calls.jsonl",
        [
            _rec(now - timedelta(hours=2), input_tokens=100, output_tokens=50),
            _rec(now - timedelta(days=3), input_tokens=1000, output_tokens=500),
        ],
    )
    summary = TokenLedger(platform_home=tmp_path).summary(now=now)
    assert summary["session_5h"]["total_tokens"] == 150
    assert summary["weekly_7d"]["total_tokens"] == 1650
