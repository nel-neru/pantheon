"""QuotaGovernor — pre-emptive throttle that sheds low-priority work near the cap.

A-1's :class:`~core.runtime.usage_gate.RateLimitGate` reacts *after* the account
hits a usage limit. The governor acts *before*: it reads the measured 5-hour
token spend from :class:`~core.runtime.token_ledger.TokenLedger` and, as spend
approaches the subscription's approximate ceiling, denies progressively
lower-priority tasks so the heavy/critical work (e.g. a due scheduled post)
still fits inside the window.

Priority classes: ``critical`` > ``standard`` > ``background``.

Decision table (per :func:`QuotaGovernor.allow`):
* rate-limit gate active        → deny everything (defer to A-1's pause)
* spend ≥ hard limit            → allow only ``critical`` (downgraded one tier)
* soft ≤ spend < hard           → deny ``background``; allow the rest, downgraded one tier
* spend < soft limit            → allow everything, no downgrade

``PANTHEON_QUOTA_GOVERNOR=0`` disables the governor (always-allow kill switch).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.runtime.token_ledger import TokenLedger
from core.runtime.usage_gate import RateLimitGate

logger = logging.getLogger(__name__)

GOVERNOR_ENV = "PANTHEON_QUOTA_GOVERNOR"
CONFIG_FILENAME = "token_quota.yaml"

PRIORITY_CRITICAL = "critical"
PRIORITY_STANDARD = "standard"
PRIORITY_BACKGROUND = "background"
_PRIORITY_RANK = {PRIORITY_BACKGROUND: 0, PRIORITY_STANDARD: 1, PRIORITY_CRITICAL: 2}

DEFAULT_WINDOW_HOURS = 5.0
DEFAULT_SOFT_LIMIT = 3_000_000
DEFAULT_HARD_LIMIT = 5_000_000


def governor_enabled() -> bool:
    return os.getenv(GOVERNOR_ENV, "1").strip().lower() not in {"0", "false", "off", "no"}


@dataclass
class Verdict:
    allowed: bool
    downgrade: bool  # True なら ModelTierRouter で light ティアへ降格すべき
    reason: str
    window_tokens: int = 0


@dataclass(frozen=True)
class QuotaRules:
    window_hours: float = DEFAULT_WINDOW_HOURS
    soft_limit_tokens: int = DEFAULT_SOFT_LIMIT
    hard_limit_tokens: int = DEFAULT_HARD_LIMIT


def _config_path() -> Path:
    from core.paths import resource_path

    return resource_path("config", CONFIG_FILENAME)


def load_rules(path: Optional[Path] = None) -> QuotaRules:
    path = path or _config_path()
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 - 設定不備はデフォルトで吸収
        logger.debug("token_quota.yaml unavailable (%s) — using built-in defaults", exc)
        return QuotaRules()
    if not isinstance(data, dict):
        return QuotaRules()

    def _num(key: str, default):
        val = data.get(key, default)
        return val if isinstance(val, (int, float)) and val > 0 else default

    return QuotaRules(
        window_hours=float(_num("window_hours", DEFAULT_WINDOW_HOURS)),
        soft_limit_tokens=int(_num("soft_limit_tokens", DEFAULT_SOFT_LIMIT)),
        hard_limit_tokens=int(_num("hard_limit_tokens", DEFAULT_HARD_LIMIT)),
    )


def save_rules(
    *,
    window_hours: Optional[float] = None,
    soft_limit_tokens: Optional[int] = None,
    hard_limit_tokens: Optional[int] = None,
    path: Optional[Path] = None,
) -> QuotaRules:
    """token_quota.yaml にトークンクォータ上限を部分更新で永続化する（SET-EXPOSE / §4 P2-5）。

    指定された項目のみ上書きし、未指定は現行値を保つ。正の数のみ受理し、不正値は無視する。
    soft が hard を超える設定は安全側に入れ替える（soft <= hard を保証）。更新後の ``QuotaRules`` を返す。
    """
    import yaml

    path = path or _config_path()
    current = load_rules(path)
    new_window = float(window_hours) if _is_pos(window_hours) else current.window_hours
    new_soft = int(soft_limit_tokens) if _is_pos(soft_limit_tokens) else current.soft_limit_tokens
    new_hard = int(hard_limit_tokens) if _is_pos(hard_limit_tokens) else current.hard_limit_tokens
    if new_soft > new_hard:  # soft は hard 以下を保証（取り違え防止）
        new_soft, new_hard = new_hard, new_soft

    payload = {
        "window_hours": new_window,
        "soft_limit_tokens": new_soft,
        "hard_limit_tokens": new_hard,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
    except OSError as exc:  # pragma: no cover - 書き込み不可は握りつぶし
        logger.warning("failed to persist token_quota.yaml: %s", exc)
    return QuotaRules(
        window_hours=new_window, soft_limit_tokens=new_soft, hard_limit_tokens=new_hard
    )


def _is_pos(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


class QuotaGovernor:
    def __init__(
        self,
        rules: Optional[QuotaRules] = None,
        *,
        ledger: Optional[TokenLedger] = None,
        gate: Optional[RateLimitGate] = None,
    ):
        self._rules = rules or load_rules()
        self._ledger = ledger or TokenLedger()
        self._gate = gate or RateLimitGate()

    def allow(self, priority: str, *, now: Optional[datetime] = None) -> Verdict:
        if not governor_enabled():
            return Verdict(True, False, "governor_disabled")

        rank = _PRIORITY_RANK.get(priority, _PRIORITY_RANK[PRIORITY_STANDARD])

        # レート制限中は A-1 の pause に委ね、新規呼び出しは全て止める。
        if self._gate.is_limited(now):
            return Verdict(False, False, "rate_limited")

        usage = self._ledger.window_usage(self._rules.window_hours, now=now)
        spent = usage.total_tokens

        if spent >= self._rules.hard_limit_tokens:
            # ハード超過: critical のみ（しかも light ティアへ降格）
            allowed = rank >= _PRIORITY_RANK[PRIORITY_CRITICAL]
            return Verdict(allowed, True, "hard_limit", window_tokens=spent)
        if spent >= self._rules.soft_limit_tokens:
            # ソフト超過: background を停止、残りは light ティアへ降格
            allowed = rank >= _PRIORITY_RANK[PRIORITY_STANDARD]
            return Verdict(allowed, True, "soft_limit", window_tokens=spent)
        return Verdict(True, False, "ok", window_tokens=spent)

    def status(self, *, now: Optional[datetime] = None) -> dict:
        usage = self._ledger.window_usage(self._rules.window_hours, now=now)
        spent = usage.total_tokens
        if self._gate.is_limited(now):
            level = "rate_limited"
        elif spent >= self._rules.hard_limit_tokens:
            level = "hard_limit"
        elif spent >= self._rules.soft_limit_tokens:
            level = "soft_limit"
        else:
            level = "ok"
        return {
            "enabled": governor_enabled(),
            "level": level,
            "window_hours": self._rules.window_hours,
            "window_tokens": spent,
            "soft_limit_tokens": self._rules.soft_limit_tokens,
            "hard_limit_tokens": self._rules.hard_limit_tokens,
        }
