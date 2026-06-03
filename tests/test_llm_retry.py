"""Tests for the LLM timeout/retry/error-normalization layer (core/llm/retry.py)."""

from __future__ import annotations

import asyncio

import pytest

from core.llm.retry import LLMError, call_with_retry, classify_exception


async def _noop_sleep(_delay: float) -> None:
    return None


async def test_success_first_try():
    async def factory():
        return 42

    assert await call_with_retry(lambda: factory(), timeout=None) == 42


async def test_retries_then_succeeds():
    calls = {"n": 0}
    delays: list[float] = []

    async def factory():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("transient")
        return "ok"

    async def fake_sleep(d):
        delays.append(d)

    result = await call_with_retry(lambda: factory(), attempts=3, sleep=fake_sleep, timeout=None)
    assert result == "ok"
    assert calls["n"] == 3
    assert delays == [0.5, 1.0]  # 指数バックオフ


async def test_non_retryable_raises_immediately():
    class Boom(Exception):
        status_code = 400

    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        raise Boom("bad request")

    with pytest.raises(LLMError) as exc_info:
        await call_with_retry(lambda: factory(), attempts=3, timeout=None)
    assert calls["n"] == 1
    assert exc_info.value.retryable is False
    assert exc_info.value.status == 400


async def test_exhausts_attempts_and_raises_llmerror():
    async def factory():
        raise ConnectionError("always down")

    delays: list[float] = []

    async def fake_sleep(d):
        delays.append(d)

    with pytest.raises(LLMError) as exc_info:
        await call_with_retry(lambda: factory(), attempts=3, sleep=fake_sleep, timeout=None)
    assert exc_info.value.retryable is True
    assert len(delays) == 2  # 3 試行の間に 2 回スリープ


async def test_timeout_is_retryable():
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return "late"

    with pytest.raises(LLMError):
        await call_with_retry(lambda: factory(), attempts=2, timeout=0.01, sleep=_noop_sleep)
    assert calls["n"] == 2


async def test_existing_llmerror_passes_through():
    async def factory():
        raise LLMError("already normalized", provider="x")

    with pytest.raises(LLMError) as exc_info:
        await call_with_retry(lambda: factory(), timeout=None)
    assert "already normalized" in str(exc_info.value)


def test_classify_exception():
    class Status:
        def __init__(self, code):
            self.status_code = code

    assert classify_exception(Status(429)) == (True, 429)
    assert classify_exception(Status(503)) == (True, 503)
    assert classify_exception(Status(400)) == (False, 400)
    assert classify_exception(Status(401)) == (False, 401)
    assert classify_exception(asyncio.TimeoutError())[0] is True
    assert classify_exception(ConnectionError())[0] is True
    assert classify_exception(Exception("rate limit exceeded"))[0] is True
    assert classify_exception(Exception("overloaded"))[0] is True
    assert classify_exception(ValueError("invalid model name"))[0] is False
