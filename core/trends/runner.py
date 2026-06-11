"""Trend collection orchestration — collect → score → dedup-store."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from core.trends.collectors.web import collect_web, load_sources
from core.trends.scoring import score_all
from core.trends.store import TrendStore

logger = logging.getLogger(__name__)


async def collect_and_store(
    *,
    platform_home: Optional[Path] = None,
    sources_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """全ソースから収集 → claude light ティアで採点 → 重複排除して保存。

    戻り値: {"collected": int, "added": int, "sources": int}
    """
    sources = load_sources(sources_path)
    items = collect_web(sources)
    await score_all(items)
    store = TrendStore(platform_home)
    added = store.add_many(items)
    summary = {"collected": len(items), "added": added, "sources": len(sources)}
    logger.info("trend collection: %s", summary)
    return summary
