"""REV-COLLECT: 収益収集オーケストレータ。

接続済みアダプタの売上を取得して :class:`~core.metrics.outcomes.OutcomeStore` へ記録し、
未接続アダプタは「接続してください」という人間タスクを一度だけ承認キューへ積む。

すべて決定論・冪等（``dedupe_on_source`` で二重計上を防ぎ、接続タスクは ``dedupe_key`` で
一度きり）。LLM 非依存。実 API 認証・取得は各アダプタ側＝human-gate。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.metrics.revenue_collectors.adapters import (
    AspRevenueCollector,
    NoteRevenueCollector,
    XRevenueCollector,
    YouTubeRevenueCollector,
)
from core.metrics.revenue_collectors.base import RevenueCollector

logger = logging.getLogger(__name__)

# 既定で巡回するアダプタ群。
DEFAULT_COLLECTORS: List[RevenueCollector] = [
    NoteRevenueCollector(),
    XRevenueCollector(),
    AspRevenueCollector(),
    YouTubeRevenueCollector(),
]


def run_revenue_collection(
    *,
    platform_home=None,
    collectors: Optional[List[RevenueCollector]] = None,
) -> Dict[str, Any]:
    """全アダプタを巡回し、接続済みは収益記録・未接続は接続タスクを積む（冪等）。

    Returns: ``{"recorded": int, "collected_sources": [...], "needs_connection": [...]}``。
    """
    if platform_home is None:
        from core.platform.state import get_platform_home

        platform_home = get_platform_home()
    home = Path(platform_home)

    from core.humans.human_tasks import enqueue_human_task
    from core.metrics.outcomes import OutcomeStore

    store = OutcomeStore(platform_home=home)
    used = DEFAULT_COLLECTORS if collectors is None else collectors

    recorded = 0
    collected_sources: List[str] = []
    needs_connection: List[str] = []

    for collector in used:
        source = getattr(collector, "source", "unknown")
        try:
            configured = collector.is_configured(home)
        except Exception as exc:  # noqa: BLE001
            logger.info("revenue collector %s is_configured failed: %s", source, exc)
            configured = False

        if not configured:
            needs_connection.append(source)
            # 接続を促す人間タスクを一度だけ積む（実認証は human-gate）。
            enqueue_human_task(
                f"{getattr(collector, 'label', source)} を接続して収益を自動収集する",
                platform_home=home,
                kind="revenue_connect",
                description=(
                    f"{source} の資格情報を ~/.pantheon/revenue_credentials/{source}.json に接続すると、"
                    "以後この収益が自動で記録されます（それまでは手動入力/CSV 取り込みが使えます）。"
                ),
                dedupe_key=f"revenue_connect:{source}",
            )
            continue

        try:
            records = collector.fetch(home) or []
        except Exception as exc:  # noqa: BLE001
            logger.info("revenue collector %s fetch failed: %s", source, exc)
            records = []

        n = 0
        for rec in records:
            try:
                store.record(
                    rec.org_name,
                    "revenue",
                    rec.amount,
                    source=rec.source,  # レコード単位の安定キー
                    note=rec.note,
                    actor=source,  # 監査: どのコレクタ由来か
                    actor_type="collector",
                    occurred_at=rec.occurred_at,
                    dedupe_on_source=True,  # 二重計上を防ぐ（冪等）
                )
                n += 1
            except Exception as exc:  # noqa: BLE001
                logger.info("revenue record failed (%s): %s", source, exc)
        recorded += n
        collected_sources.append(source)

    return {
        "recorded": recorded,
        "collected_sources": collected_sources,
        "needs_connection": needs_connection,
    }
