"""Trend collection orchestration — collect → score → dedup-store."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from core.trends.collectors.web import collect_web, load_sources
from core.trends.collectors.youtube import collect_youtube, load_channels
from core.trends.scoring import score_all
from core.trends.store import TrendStore

logger = logging.getLogger(__name__)


async def collect_and_store(
    *,
    platform_home: Optional[Path] = None,
    sources_path: Optional[Path] = None,
    with_captions: bool = False,
) -> Dict[str, Any]:
    """全ソース（RSS/Atom + YouTube）から収集 → light ティア採点 → 重複排除保存。

    戻り値: {"collected": int, "added": int, "sources": int, "web": int, "youtube": int}
    """
    sources = load_sources(sources_path)
    channels = load_channels(sources_path)
    web_items = collect_web(sources)
    yt_items = collect_youtube(channels, with_captions=with_captions)
    items = web_items + yt_items
    await score_all(items)
    store = TrendStore(platform_home)
    added = store.add_many(items)
    summary = {
        "collected": len(items),
        "added": added,
        "sources": len(sources) + len(channels),
        "web": len(web_items),
        "youtube": len(yt_items),
    }
    logger.info("trend collection: %s", summary)
    return summary
