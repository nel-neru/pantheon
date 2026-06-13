"""Trend collection orchestration — collect → score → dedup-store."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from core.trends.collectors.web import collect_web, load_sources
from core.trends.collectors.youtube import collect_youtube, load_channels
from core.trends.models import TrendItem
from core.trends.scoring import score_all
from core.trends.store import TrendStore
from core.trends.trend_dedup import dedupe_trends

logger = logging.getLogger(__name__)


def _dedupe_items(items: list[TrendItem]) -> list[TrendItem]:
    """採点済み TrendItem 群を意味的に重複排除する（P2.5・store の hash 完全一致を補完）。

    url の末尾スラッシュ/大小文字差や、別ソースから来た同一トピックを ``trend_dedup``
    で正規化キー単位に畳み込み、同一キーは score 最大の 1 件のみ残す。store の hash
    dedup より広いキーで、保存前に near-duplicate を 1 件へ集約する。
    """
    wrapped = [{"url": it.url, "title": it.title, "score": it.score, "_item": it} for it in items]
    return [w["_item"] for w in dedupe_trends(wrapped)]


async def collect_and_store(
    *,
    platform_home: Optional[Path] = None,
    sources_path: Optional[Path] = None,
    with_captions: bool = False,
) -> Dict[str, Any]:
    """全ソース（RSS/Atom + YouTube）から収集 → light ティア採点 → 重複排除保存。

    戻り値: {"collected": int, "added": int, "sources": int, "web": int, "youtube": int}
    """
    import asyncio

    sources = load_sources(sources_path)
    channels = load_channels(sources_path)
    # collect_web/collect_youtube は同期ブロッキング HTTP。イベントループ（FastAPI
    # の /api/trends/collect 等）を塞がないよう worker thread で実行する。
    web_items = await asyncio.to_thread(collect_web, sources)
    yt_items = await asyncio.to_thread(collect_youtube, channels, with_captions=with_captions)
    items = web_items + yt_items
    await score_all(items)
    # P2.5: 採点後・保存前に意味的重複（url 正規化/title）を最高スコア1件へ畳み込む。
    deduped = _dedupe_items(items)
    store = TrendStore(platform_home)
    added = store.add_many(deduped)
    summary = {
        "collected": len(items),
        "deduped": len(items) - len(deduped),
        "added": added,
        "sources": len(sources) + len(channels),
        "web": len(web_items),
        "youtube": len(yt_items),
    }
    logger.info("trend collection: %s", summary)
    return summary
