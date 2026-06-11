"""Tests for exponential backoff (core.runtime.retry)."""

from __future__ import annotations

import pytest

from core.runtime.claude_code import ClaudeRateLimitedError
from core.runtime.rate_limit import RateLimitInfo
from core.runtime.retry import backoff_delays, with_backoff


def test_backoff_delays_progression():
    assert backoff_delays(3, base=5.0, factor=5.0, max_delay=7200.0) == [5.0, 25.0, 125.0]
    assert backoff_delays(0, base=5.0, factor=5.0, max_delay=7200.0) == []


def test_backoff_delays_capped():
    delays = backoff_delays(5, base=5.0, factor=5.0, max_delay=100.0)
    assert delays == [5.0, 25.0, 100.0, 100.0, 100.0]


async def test_succeeds_first_try():
    calls = []

    async def fn():
        calls.append(1)
        return "ok"

    result = await with_backoff(fn, retries=3, sleep=_no_sleep)
    assert result == "ok"
    assert len(calls) == 1


async def test_retries_then_succeeds():
    calls = []

    async def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("transient")
        return "ok"

    result = await with_backoff(fn, retries=3, sleep=_no_sleep)
    assert result == "ok"
    assert len(calls) == 3


async def test_exhausts_and_reraises():
    calls = []

    async def fn():
        calls.append(1)
        raise ValueError("always fails")

    with pytest.raises(ValueError):
        await with_backoff(fn, retries=2, sleep=_no_sleep)
    assert len(calls) == 3  # 初回 + 2 リトライ


async def test_rate_limit_error_not_retried():
    calls = []

    async def fn():
        calls.append(1)
        raise ClaudeRateLimitedError("limit", RateLimitInfo(limited=True))

    with pytest.raises(ClaudeRateLimitedError):
        await with_backoff(fn, retries=5, sleep=_no_sleep)
    assert len(calls) == 1  # gate に委譲。再試行しない


async def test_only_retries_listed_exceptions():
    calls = []

    async def fn():
        calls.append(1)
        raise KeyError("not in retry_on")

    with pytest.raises(KeyError):
        await with_backoff(fn, retries=3, retry_on=(ValueError,), sleep=_no_sleep)
    assert len(calls) == 1


async def test_sleep_called_with_backoff_delays():
    slept: list[float] = []

    async def record(d):
        slept.append(d)

    calls = []

    async def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("x")
        return "done"

    await with_backoff(fn, retries=3, base=2.0, factor=3.0, max_delay=100.0, sleep=record)
    assert slept == [2.0, 6.0]


async def _no_sleep(_seconds: float) -> None:
    return None
