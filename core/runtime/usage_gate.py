"""Cross-process rate-limit gate shared by every Claude generation path.

Pantheon runs several long-lived processes that all call the same local
``claude`` CLI (improvement daemon, content daemon, web server, CLI commands).
A usage limit hit by any one of them applies to the whole account, so the
limit state must be visible to *all* of them. This module persists that state
to a single small JSON file under the platform home
(``~/.pantheon/rate_limit_state.json``) using atomic writes, and exposes it
through :class:`RateLimitGate`:

* ``report(info)``  — record a detected limit (called from ``claude_code``)
* ``current(now)``  — the active :class:`RateLimitInfo`, auto-clearing once
  ``reset_at`` has passed (this is what makes "resume when the window
  reopens" automatic)
* ``is_limited(now)`` / ``seconds_until_clear(now)`` — convenience checks

The gate stores state only; deciding what to do (skip the call, pause the
loop, surface it in the UI) stays with the callers.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.runtime.rate_limit import RateLimitInfo

logger = logging.getLogger(__name__)

STATE_FILENAME = "rate_limit_state.json"
# Escape hatch: a truthy value disables the *pre-call block* in claude_code
# (detection/reporting still happens). For tests and emergencies.
BYPASS_ENV = "PANTHEON_NO_RATE_GATE"

_TRUTHY = {"1", "true", "yes", "on"}


def gate_bypassed() -> bool:
    """True when the pre-call rate gate is disabled via :data:`BYPASS_ENV`."""
    return os.getenv(BYPASS_ENV, "").strip().lower() in _TRUTHY


class RateLimitGate:
    """File-backed, cross-process view of the current Claude usage limit."""

    def __init__(self, state_path: Optional[Path] = None):
        self._explicit_path = Path(state_path) if state_path else None

    @property
    def state_path(self) -> Path:
        if self._explicit_path is not None:
            return self._explicit_path
        # Resolved lazily on every access so tests that monkeypatch
        # get_platform_home (the established conftest pattern) are honoured.
        from core.platform.state import get_platform_home

        return Path(get_platform_home()) / STATE_FILENAME

    # ---- writes ----
    def report(self, info: RateLimitInfo) -> None:
        """Persist a detected limit. No-op for ``limited=False`` (use clear())."""
        if not info.limited:
            return
        record: Dict[str, Any] = {
            "limited": True,
            "reset_at": info.reset_at.isoformat() if info.reset_at else None,
            "scope": info.scope,
            "message": info.message,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }
        path = self.state_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False, indent=2))
                os.replace(tmp_name, path)
            except BaseException:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
        except OSError as exc:  # best-effort: the gate must never break a call
            logger.warning("failed to persist rate-limit state: %s", exc)

    def clear(self) -> None:
        try:
            self.state_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.debug("failed to clear rate-limit state: %s", exc)

    # ---- reads ----
    def current(self, now: Optional[datetime] = None) -> Optional[RateLimitInfo]:
        """The active limit, or ``None``. Auto-clears once ``reset_at`` passes."""
        path = self.state_path
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            data = json.loads(raw)
        except ValueError:
            self.clear()
            return None
        if not isinstance(data, dict) or not data.get("limited"):
            return None

        reset_at: Optional[datetime] = None
        raw_reset = data.get("reset_at")
        if isinstance(raw_reset, str) and raw_reset:
            try:
                reset_at = datetime.fromisoformat(raw_reset)
            except ValueError:
                reset_at = None
            if reset_at is not None and reset_at.tzinfo is None:
                reset_at = reset_at.replace(tzinfo=timezone.utc)

        now = now or datetime.now(timezone.utc)
        if reset_at is not None and reset_at <= now:
            # 制限窓が開いた — ここで自動 clear するのが「解除されたら再開」の起点。
            self.clear()
            return None

        return RateLimitInfo(
            limited=True,
            reset_at=reset_at,
            scope=str(data.get("scope") or "session"),
            message=str(data.get("message") or ""),
        )

    def is_limited(self, now: Optional[datetime] = None) -> bool:
        return self.current(now) is not None

    def seconds_until_clear(self, now: Optional[datetime] = None) -> float:
        now = now or datetime.now(timezone.utc)
        info = self.current(now)
        if info is None:
            return 0.0
        return info.seconds_until_reset(now)
