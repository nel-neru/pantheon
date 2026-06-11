"""TokenLedger — read-only aggregation of measured token usage over time windows.

The single source of truth is ``~/.pantheon/claude_calls.jsonl``, which
``core.runtime.claude_code`` already appends to on every real ``claude`` call
(including the measured ``input_tokens`` / ``output_tokens`` / ``task_type``
added in A-4). This module only *reads and aggregates* it — it never writes —
so it can be consulted from any process (schedulers, governor, web API) to
answer "how much have we spent in the last 5 hours / 7 days?".

When a record lacks measured tokens (older ``claude`` CLI), the ledger falls
back to a char-count estimate (``prompt_chars + system_chars`` for input,
a small fixed estimate for output) so the quota still functions.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 実測トークンが無いレコードの概算: 1 token ≈ 4 文字。
_CHARS_PER_TOKEN = 4
# 出力トークン不明時の控えめな既定（過小評価で throttle が緩くなりすぎないよう）。
_DEFAULT_OUTPUT_TOKENS_ESTIMATE = 500

WINDOW_SESSION_HOURS = 5.0
WINDOW_WEEKLY_HOURS = 24.0 * 7


@dataclass
class WindowUsage:
    window_hours: float
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    total_cost_usd: float = 0.0
    measured_calls: int = 0  # 実測トークンが取れた呼び出し数
    estimated_calls: int = 0  # 文字数概算にフォールバックした呼び出し数

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def _timing_log_path(platform_home: Optional[Path]) -> Path:
    if platform_home is None:
        from core.platform.state import get_platform_home

        platform_home = get_platform_home()
    return Path(platform_home) / "claude_calls.jsonl"


def _parse_ts(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _int(value: object) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class TokenLedger:
    def __init__(self, platform_home: Optional[Path] = None):
        self._explicit_home = Path(platform_home) if platform_home else None

    @property
    def log_path(self) -> Path:
        return _timing_log_path(self._explicit_home)

    def window_usage(
        self, window_hours: float = WINDOW_SESSION_HOURS, *, now: Optional[datetime] = None
    ) -> WindowUsage:
        """直近 ``window_hours`` 時間の集計（実測優先、無ければ文字数概算）。"""
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=window_hours)
        usage = WindowUsage(window_hours=window_hours)

        path = self.log_path
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return usage

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            ts = _parse_ts(rec.get("ts"))
            if ts is None or ts < cutoff:
                continue

            usage.calls += 1
            in_tok = _int(rec.get("input_tokens"))
            out_tok = _int(rec.get("output_tokens"))
            cache_tok = _int(rec.get("cache_read_tokens"))
            cost = rec.get("total_cost_usd")

            if in_tok is not None or out_tok is not None:
                usage.measured_calls += 1
                usage.input_tokens += in_tok or 0
                usage.output_tokens += out_tok or 0
                usage.cache_read_tokens += cache_tok or 0
            else:
                # 旧 CLI: 文字数からの概算へフォールバック
                usage.estimated_calls += 1
                prompt_chars = _int(rec.get("prompt_chars")) or 0
                system_chars = _int(rec.get("system_chars")) or 0
                usage.input_tokens += (prompt_chars + system_chars) // _CHARS_PER_TOKEN
                usage.output_tokens += _DEFAULT_OUTPUT_TOKENS_ESTIMATE
            if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                usage.total_cost_usd += float(cost)

        return usage

    def summary(self, *, now: Optional[datetime] = None) -> dict:
        """5h / 7d 窓の集計をまとめて返す（/api/usage/summary 用）。"""
        session = self.window_usage(WINDOW_SESSION_HOURS, now=now)
        weekly = self.window_usage(WINDOW_WEEKLY_HOURS, now=now)

        def _fmt(u: WindowUsage) -> dict:
            return {
                "window_hours": u.window_hours,
                "calls": u.calls,
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
                "cache_read_tokens": u.cache_read_tokens,
                "total_tokens": u.total_tokens,
                "total_cost_usd": round(u.total_cost_usd, 6),
                "measured_calls": u.measured_calls,
                "estimated_calls": u.estimated_calls,
            }

        return {"session_5h": _fmt(session), "weekly_7d": _fmt(weekly)}
