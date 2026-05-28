"""
AdaptiveCacheManager — キャッシュ戦略自動最適化 (K-14)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class CacheEntry:
    key: str
    value: Any
    access_count: int = 0
    last_accessed: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AdaptiveCacheManager:
    """Tiny LFU cache with hit-rate tracking."""

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self._entries: dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            self._misses += 1
            return None
        self._hits += 1
        entry.access_count += 1
        entry.last_accessed = datetime.now(timezone.utc).isoformat()
        return entry.value

    def set(self, key: str, value: Any) -> None:
        if key in self._entries:
            entry = self._entries[key]
            entry.value = value
            entry.last_accessed = datetime.now(timezone.utc).isoformat()
            return
        if len(self._entries) >= self.max_size:
            evict_key = min(
                self._entries,
                key=lambda item: (
                    self._entries[item].access_count,
                    self._entries[item].last_accessed,
                    self._entries[item].created_at,
                ),
            )
            self._entries.pop(evict_key, None)
        self._entries[key] = CacheEntry(key=key, value=value)

    def get_hit_rate(self) -> float:
        total = self._hits + self._misses
        return round(self._hits / total, 3) if total else 0.0

    def get_stats(self) -> dict:
        most_accessed_key = None
        if self._entries:
            most_accessed_key = max(self._entries.values(), key=lambda entry: entry.access_count).key
        return {
            "size": len(self._entries),
            "hit_rate": self.get_hit_rate(),
            "most_accessed_key": most_accessed_key,
        }
