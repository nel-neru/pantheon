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
    sources: Optional[set[str]] = None,
    grok_query: Optional[str] = None,
) -> Dict[str, Any]:
    """選択した collector（RSS/Atom + YouTube + 任意で Grok）から収集 → 採点 → 重複排除保存。

    ``sources`` で回す collector を選ぶ（None = {"web", "youtube"}・後方互換）。Grok は
    ``"grok" in sources`` か ``grok_query`` 指定で有効になり、Playwright の async_api なので
    worker thread で包まず直接 await する。未接続/未導入/失効なら捏造せず 0 件＋
    ``grok_needs_reconnect`` を立てて正直に返す。

    戻り値: {"collected", "deduped", "added", "sources", "web", "youtube", "grok",
             "grok_needs_reconnect"}
    """
    import asyncio

    sel = sources if sources is not None else {"web", "youtube"}

    web_list = load_sources(sources_path) if "web" in sel else []
    channels = load_channels(sources_path) if "youtube" in sel else []
    # collect_web/collect_youtube は同期ブロッキング HTTP。イベントループ（FastAPI
    # の /api/trends/collect 等）を塞がないよう worker thread で実行する。
    web_items = await asyncio.to_thread(collect_web, web_list) if web_list else []
    yt_items = (
        await asyncio.to_thread(collect_youtube, channels, with_captions=with_captions)
        if channels
        else []
    )

    grok_items: list[TrendItem] = []
    grok_reconnect = False
    grok_source_count = 0
    if "grok" in sel or grok_query:
        from core.trends.collectors.grok import collect_grok, load_grok_queries

        queries, enabled = load_grok_queries(sources_path)
        if grok_query or (enabled and queries):
            grok_source_count = 1 if grok_query else len(queries)
            try:
                # Grok は async（Playwright）。直接 await。失敗しても web/youtube を巻き込まない。
                grok_items, grok_reconnect = await collect_grok(queries, grok_query=grok_query)
            except Exception as exc:  # noqa: BLE001 — Grok 失敗で他ソースを落とさない
                logger.info("grok collect failed: %s", exc)
                grok_reconnect = True

    items = web_items + yt_items + grok_items
    await score_all(items)
    # P2.5: 採点後・保存前に意味的重複（url 正規化/title）を最高スコア1件へ畳み込む。
    deduped = _dedupe_items(items)
    store = TrendStore(platform_home)
    added = store.add_many(deduped)
    summary = {
        "collected": len(items),
        "deduped": len(items) - len(deduped),
        "added": added,
        "sources": len(web_list) + len(channels) + grok_source_count,
        "web": len(web_items),
        "youtube": len(yt_items),
        "grok": len(grok_items),
        "grok_needs_reconnect": grok_reconnect,
    }
    logger.info("trend collection: %s", summary)
    return summary
