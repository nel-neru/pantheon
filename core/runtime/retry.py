"""Exponential backoff for transient failures (publish, flaky CLI calls).

Deliberately **excludes** :class:`~core.runtime.claude_code.ClaudeRateLimitedError`:
rate limits are not transient and are already handled by the shared
:class:`~core.runtime.usage_gate.RateLimitGate` (the schedulers pause until the
window reopens). Retrying a rate-limited call would only spawn doomed
subprocesses and waste the very token budget A-1/A-5 protect.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional, Sequence, Type, TypeVar

from core.runtime.claude_code import ClaudeRateLimitedError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def backoff_delays(retries: int, base: float, factor: float, max_delay: float) -> list[float]:
    """The delay (seconds) before each retry attempt. Pure/testable."""
    delays: list[float] = []
    delay = base
    for _ in range(max(0, retries)):
        delays.append(min(delay, max_delay))
        delay *= factor
    return delays


async def with_backoff(
    fn: Callable[[], Awaitable[T]],
    *,
    retries: int = 3,
    base: float = 5.0,
    factor: float = 5.0,
    max_delay: float = 7200.0,
    retry_on: Sequence[Type[BaseException]] = (Exception,),
    sleep: Optional[Callable[[float], Awaitable[None]]] = None,
) -> T:
    """Call ``fn`` with exponential backoff on the given exception types.

    :class:`ClaudeRateLimitedError` is never retried (re-raised immediately),
    even if it is an instance of a type in ``retry_on`` — the rate-limit gate
    owns that case. The last failure is re-raised after exhausting ``retries``.
    """
    sleep = sleep or asyncio.sleep
    delays = backoff_delays(retries, base, factor, max_delay)
    attempt = 0
    while True:
        try:
            return await fn()
        except ClaudeRateLimitedError:
            raise  # gate に委譲。再試行はトークンの無駄。
        except retry_on as exc:  # type: ignore[misc]
            if attempt >= len(delays):
                raise
            delay = delays[attempt]
            logger.info(
                "retry %d/%d after %.1fs (%s: %s)",
                attempt + 1,
                len(delays),
                delay,
                type(exc).__name__,
                exc,
            )
            await sleep(delay)
            attempt += 1
