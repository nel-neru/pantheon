"""
usage — LLM トークン使用量のトラッキング（B7）

各 provider の generate が返す usage を provider/model 別に集計する。
「どのAIでも全機能」を実用的に運用するため、コスト把握の基礎データを提供する。

v1 はプロセス内メモリ集計（サーバ再起動でリセット）。永続化は後続。
記録は best-effort（記録失敗が LLM 呼び出しを壊さない）。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from threading import Lock
from typing import Any, Dict, Optional

__all__ = ["UsageRecord", "UsageTracker", "get_usage_tracker", "record_usage", "reset_usage"]


@dataclass
class UsageRecord:
    provider: str
    model: str
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UsageTracker:
    """provider/model 別のトークン使用量を集計する（スレッドセーフ）。"""

    _records: Dict[tuple[str, str], UsageRecord] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def record(self, provider: str, model: Optional[str], usage: Optional[Dict[str, Any]]) -> None:
        provider = provider or "unknown"
        model = model or "unknown"
        with self._lock:
            rec = self._records.get((provider, model))
            if rec is None:
                rec = UsageRecord(provider=provider, model=model)
                self._records[(provider, model)] = rec
            rec.calls += 1
            if usage:
                prompt = int(usage.get("prompt_tokens") or 0)
                completion = int(usage.get("completion_tokens") or 0)
                total = int(usage.get("total_tokens") or (prompt + completion))
                rec.prompt_tokens += prompt
                rec.completion_tokens += completion
                rec.total_tokens += total

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            by_model = [rec.to_dict() for rec in self._records.values()]
        by_provider: Dict[str, Dict[str, int]] = {}
        totals = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        for rec in by_model:
            prov = by_provider.setdefault(
                rec["provider"], {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            )
            for key in ("calls", "prompt_tokens", "completion_tokens", "total_tokens"):
                prov[key] += rec[key]
                totals[key] += rec[key]
        return {"by_model": by_model, "by_provider": by_provider, "totals": totals}

    def reset(self) -> None:
        with self._lock:
            self._records.clear()


_tracker: Optional[UsageTracker] = None


def get_usage_tracker() -> UsageTracker:
    global _tracker
    if _tracker is None:
        _tracker = UsageTracker()
    return _tracker


def record_usage(provider: str, model: Optional[str], usage: Optional[Dict[str, Any]]) -> None:
    """使用量を記録する（best-effort: 例外は握りつぶし LLM 呼び出しを壊さない）。"""
    try:
        get_usage_tracker().record(provider, model, usage)
    except Exception:  # noqa: BLE001 — トラッキング失敗は本処理に影響させない
        pass


def reset_usage() -> None:
    get_usage_tracker().reset()
