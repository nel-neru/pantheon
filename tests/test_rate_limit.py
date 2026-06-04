"""Tests for Claude rate-limit detection / reset-time parsing."""

from __future__ import annotations

from datetime import datetime, timezone

from core.runtime.rate_limit import DEFAULT_BACKOFF, MAX_BACKOFF, detect_rate_limit

NOW = datetime(2026, 6, 4, 12, 0, 0, tzinfo=timezone.utc)


def test_no_limit_when_no_signal():
    info = detect_rate_limit("All good. Task completed successfully.", now=NOW)
    assert info.limited is False
    assert info.reset_at is None


def test_detects_usage_limit_with_relative_time():
    info = detect_rate_limit("Claude usage limit reached. Try again in 30 minutes.", now=NOW)
    assert info.limited is True
    assert info.reset_at is not None
    assert abs(info.seconds_until_reset(NOW) - 1800) < 5


def test_detects_iso_reset_time():
    info = detect_rate_limit(
        "rate limit reached; your limit will reset at 2026-06-04T15:00:00Z", now=NOW
    )
    assert info.limited is True
    assert info.reset_at == datetime(2026, 6, 4, 15, 0, 0, tzinfo=timezone.utc)


def test_detects_429():
    info = detect_rate_limit("HTTP 429: too many requests", now=NOW)
    assert info.limited is True
    assert info.reset_at is not None


def test_weekly_scope_detected():
    info = detect_rate_limit("You have hit your weekly usage limit.", now=NOW)
    assert info.limited is True
    assert info.scope == "weekly"


def test_unparseable_time_falls_back_to_backoff():
    info = detect_rate_limit("usage limit reached, please slow down", now=NOW)
    assert info.limited is True
    # session-scope fallback is the default backoff
    assert abs(info.seconds_until_reset(NOW) - DEFAULT_BACKOFF.total_seconds()) < 5


def test_reset_time_is_clamped_to_max():
    info = detect_rate_limit("usage limit; try again in 999 hours", now=NOW)
    assert info.limited is True
    assert info.seconds_until_reset(NOW) <= MAX_BACKOFF.total_seconds() + 1


def test_past_clock_time_rolls_to_next_day():
    # "reset at 11am" when now is 12:00 UTC -> next day (always in the future)
    info = detect_rate_limit("Your limit will reset at 11am", now=NOW)
    assert info.limited is True
    assert info.reset_at > NOW
