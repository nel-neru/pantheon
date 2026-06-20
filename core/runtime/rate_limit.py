"""
Claude Code rate-limit detection + reset-time parsing.

When a headless ``claude -p`` agent hits the 5-hour or weekly (7-day) usage
limit, the CLI stops and prints a message naming when the limit resets. Pantheon
uses :func:`detect_rate_limit` to recognise that condition from an agent's
captured output and to work out *when* it is worth retrying, so the orchestrator
can automatically resume the agent once the window reopens (instead of leaving
it failed).

The parser is intentionally forgiving: it recognises the common phrasings
("usage limit reached", "rate limit", HTTP 429, "try again in N minutes",
"resets at 10pm", ISO timestamps) and always returns a *best-effort* reset time,
falling back to a bounded backoff when no explicit time is given.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

# Default backoff when a limit is detected but no reset time can be parsed.
DEFAULT_BACKOFF = timedelta(hours=1)
# Cap any parsed/relative wait so a mis-parse can't strand an agent for days.
MAX_BACKOFF = timedelta(hours=24)

_LIMIT_SIGNALS = (
    "usage limit",
    "session limit",  # "You've hit your session limit · resets 3:20am"
    "weekly limit",
    "rate limit",
    "rate_limit",
    "rate-limit",
    "too many requests",
    "429",
    "limit reached",
    "limit will reset",
    "quota",
)

# Anchored phrasings that (near-)unambiguously mean a Claude usage limit.
# Used by :func:`detect_rate_limit_strict` when scanning *successful* output,
# where the loose signals above ("429", "quota", "rate limit") false-positive
# on legitimate generations — e.g. an X-post draft mentioning "API の rate
# limit", "1,429件", or a result JSON whose stats contain ``duration_ms":14290``.
_STRICT_LIMIT_SIGNALS = (
    "usage limit",
    "session limit",
    "weekly limit",
    "hit your limit",
    "limit reached",
    "limit will reset",
    "limit resets",
    "too many requests",
    "rate_limit_error",
    "rate limit exceeded",
    "http 429",
    "status 429",
    "error 429",
)

_SCOPE_WEEKLY = ("weekly", "7-day", "7 day", "per week", "this week")


@dataclass
class RateLimitInfo:
    """The outcome of inspecting agent output for a rate limit."""

    limited: bool
    reset_at: Optional[datetime] = None  # timezone-aware UTC
    scope: str = "session"  # "session" (5h) | "weekly" (7d)
    message: str = ""

    def seconds_until_reset(self, now: Optional[datetime] = None) -> float:
        if self.reset_at is None:
            return DEFAULT_BACKOFF.total_seconds()
        now = now or datetime.now(timezone.utc)
        return max(0.0, (self.reset_at - now).total_seconds())


def _clamp(reset_at: datetime, now: datetime) -> datetime:
    if reset_at <= now:
        return now + DEFAULT_BACKOFF
    if reset_at - now > MAX_BACKOFF:
        return now + MAX_BACKOFF
    return reset_at


def _parse_relative(text: str, now: datetime) -> Optional[datetime]:
    # "try again in 3 hours", "retry in 45 minutes", "in 30 seconds"
    m = re.search(r"\bin\s+(\d+)\s*(second|minute|hour|day)s?\b", text, re.I)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    # 正規表現が将来ドリフトして想定外の unit を拾っても KeyError で落ちないよう .get で守る。
    delta = {
        "second": timedelta(seconds=n),
        "minute": timedelta(minutes=n),
        "hour": timedelta(hours=n),
        "day": timedelta(days=n),
    }.get(unit, DEFAULT_BACKOFF)
    return now + delta


def _parse_iso(text: str) -> Optional[datetime]:
    m = re.search(r"\b(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)\b", text)
    if not m:
        return None
    raw = m.group(1).replace(" ", "T")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_clock(text: str, now: datetime) -> Optional[datetime]:
    # "reset at 10pm", "resets at 10:30 pm", "at 22:00" -> next occurrence (local)
    m = re.search(
        r"\b(?:reset|resets|again)\b[^0-9]{0,12}(\d{1,2})(?::(\d{2}))?\s*([ap]m)?", text, re.I
    )
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = (m.group(3) or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    local_now = now.astimezone()
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def _build_limited_info(text: str, low: str, now: datetime) -> RateLimitInfo:
    """Construct a ``limited=True`` info with best-effort reset-time parsing."""
    scope = "weekly" if any(s in low for s in _SCOPE_WEEKLY) else "session"
    reset_at = _parse_iso(text) or _parse_relative(low, now) or _parse_clock(low, now)
    if reset_at is None:
        reset_at = now + (timedelta(hours=6) if scope == "weekly" else DEFAULT_BACKOFF)
    reset_at = _clamp(reset_at, now)
    snippet = text.strip().splitlines()[-1][:200] if text.strip() else ""
    return RateLimitInfo(limited=True, reset_at=reset_at, scope=scope, message=snippet)


def detect_rate_limit(text: Optional[str], *, now: Optional[datetime] = None) -> RateLimitInfo:
    """Inspect captured agent output for a Claude usage/rate limit.

    Returns ``RateLimitInfo(limited=False)`` when no limit is detected. When a
    limit is found, ``reset_at`` is a best-effort timezone-aware UTC time
    (clamped to a sane range), falling back to a bounded backoff.
    """
    if not text:
        return RateLimitInfo(limited=False)
    low = text.lower()
    if not any(sig in low for sig in _LIMIT_SIGNALS):
        return RateLimitInfo(limited=False)
    return _build_limited_info(text, low, now or datetime.now(timezone.utc))


def detect_rate_limit_strict(
    text: Optional[str], *, now: Optional[datetime] = None
) -> RateLimitInfo:
    """Like :func:`detect_rate_limit`, but only anchored CLI limit phrasings.

    Use this when scanning output that may be a *legitimate generation result*
    (exit-0 success text, completed-agent logs): the loose signals match bare
    substrings like "429"/"quota"/"rate limit" that occur naturally in normal
    content, and a false positive here pauses every Pantheon process via the
    shared :class:`~core.runtime.usage_gate.RateLimitGate`. Reset-time parsing
    and clamping are shared with :func:`detect_rate_limit`.
    """
    if not text:
        return RateLimitInfo(limited=False)
    low = text.lower()
    if not any(sig in low for sig in _STRICT_LIMIT_SIGNALS):
        return RateLimitInfo(limited=False)
    return _build_limited_info(text, low, now or datetime.now(timezone.utc))
