"""
HTTP リクエストメトリクス（J4）。

処理件数・エラー数・平均処理時間・ステータス別件数をスレッドセーフに集計する
軽量コレクター。ミドルウェアが `record()` を呼び、`GET /api/metrics` が `snapshot()`
を返す。LLM 呼数/トークンは `core/llm/usage.py`（UsageTracker, B7）が別途担当。
"""

from __future__ import annotations

import threading
from typing import Any, Dict

__all__ = ["RequestMetrics", "get_request_metrics"]


class RequestMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._count = 0
        self._errors = 0
        self._total_ms = 0.0
        self._by_status: Dict[int, int] = {}

    def record(self, status_code: int, duration_ms: float) -> None:
        with self._lock:
            self._count += 1
            self._total_ms += duration_ms
            self._by_status[status_code] = self._by_status.get(status_code, 0) + 1
            if status_code >= 500:
                self._errors += 1

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            avg = self._total_ms / self._count if self._count else 0.0
            return {
                "requests": self._count,
                "errors": self._errors,
                "avg_duration_ms": round(avg, 2),
                "by_status": {str(k): v for k, v in sorted(self._by_status.items())},
            }

    def reset(self) -> None:
        with self._lock:
            self._count = 0
            self._errors = 0
            self._total_ms = 0.0
            self._by_status = {}


_metrics = RequestMetrics()


def get_request_metrics() -> RequestMetrics:
    """プロセス共有の RequestMetrics を返す。"""
    return _metrics
