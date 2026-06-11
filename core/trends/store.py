"""TrendStore — append-only JSONL store with content-hash dedup."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

from core.trends.models import TrendItem

logger = logging.getLogger(__name__)

STORE_DIRNAME = "trends"
STORE_FILENAME = "trends.jsonl"


class TrendStore:
    def __init__(self, platform_home: Optional[Path] = None):
        if platform_home is None:
            from core.platform.state import get_platform_home

            platform_home = get_platform_home()
        self._dir = Path(platform_home) / STORE_DIRNAME
        self.path = self._dir / STORE_FILENAME

    def _iter_raw(self) -> List[dict]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out: List[dict] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                out.append(rec)
        return out

    def seen_hashes(self) -> set[str]:
        return {h for r in self._iter_raw() if (h := r.get("hash"))}

    def add(self, item: TrendItem, *, seen: Optional[set[str]] = None) -> bool:
        """新規なら追記して True。重複（同 hash 既存）なら False。

        ``seen`` を渡すと既存 hash の再読込を省ける（``add_many`` のバッチ用）。
        """
        item.ensure_hash()
        known = seen if seen is not None else self.seen_hashes()
        if item.hash in known:
            return False
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
            return True
        except OSError as exc:
            logger.warning("failed to persist trend: %s", exc)
            return False

    def add_many(self, items: List[TrendItem]) -> int:
        """複数追加し、新規に追記できた件数を返す（同バッチ内の重複も排除）。

        既存 hash は 1 度だけ読み込み、以降はメモリ上で突合する（O(n)）。
        """
        seen = self.seen_hashes()
        added = 0
        for item in items:
            item.ensure_hash()
            if item.hash in seen:
                continue
            if self.add(item, seen=seen):
                seen.add(item.hash)
                added += 1
        return added

    def list(
        self,
        *,
        limit: int = 50,
        source: Optional[str] = None,
        genre: Optional[str] = None,
        min_score: float = 0.0,
    ) -> List[TrendItem]:
        items = [TrendItem.from_dict(r) for r in self._iter_raw()]
        if source:
            items = [i for i in items if i.source == source]
        if genre:
            items = [i for i in items if i.genre == genre]
        if min_score > 0:
            items = [i for i in items if i.score >= min_score]
        # スコア降順 → 新しい順
        items.sort(key=lambda i: (i.score, i.collected_at), reverse=True)
        return items[:limit]
