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
from datetime import datetime, time, timedelta, timezone
from typing import Optional

# Default backoff when a limit is detected but no reset time can be parsed.
DEFAULT_BACKOFF = timedelta(hours=1)
# Cap any parsed/relative wait so a mis-parse can't strand an agent for days.
MAX_BACKOFF = timedelta(hours=24)

_LIMIT_SIGNALS = (
    "usage limit",
    "rate limit",
    "rate_limit",
    "rate-limit",
    "too many requests",
    "429",
    "limit reached",
    "limit will reset",
    "quota",
)

_SCOPE_WEEKLY = ("weekly", "7-day", "7 day", "per week", "this week")


@dataclass
class RateLimitInfo:
    """The outcome of inspecting agent output for a rate limit."""

    limited: bool
    reset_at: Optional[datetime] = None   # timezone-aware UTC
    scope: str = "session"                # "session" (5h) | "weekly" (7d)
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
    delta = {
        "second": timedelta(seconds=n),
        "minute": timedelta(minutes=n),
        "hour": timedelta(hours=n),
        "day": timedelta(days=n),
    }[unit]
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
    m = re.search(r"\b(?:reset|resets|again)\b[^0-9]{0,12}(\d{1,2})(?::(\d{2}))?\s*([ap]m)?", text, re.I)
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

    now = now or datetime.now(timezone.utc)
    scope = "weekly" if any(s in low for s in _SCOPE_WEEKLY) else "session"

    reset_at = _parse_iso(text) or _parse_relative(low, now) or _parse_clock(low, now)
    if reset_at is None:
        reset_at = now + (timedelta(hours=6) if scope == "weekly" else DEFAULT_BACKOFF)
    reset_at = _clamp(reset_at, now)

    snippet = text.strip().splitlines()[-1][:200] if text.strip() else ""
    return RateLimitInfo(limited=True, reset_at=reset_at, scope=scope, message=snippet)
