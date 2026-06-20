"""WIRE-B: トレンド → 新規事業（新会社）提案 を承認ゲートへ配線する（計画 §P2.1）。

P2.1 の純粋関数 :func:`core.trends.business_proposal.trend_to_business_proposal`
（高スコアトレンド1件 → 新会社設計 dict: genre / suggested_divisions / rationale）を、
保存済み :class:`~core.trends.store.TrendStore` のトレンドに適用し、人手承認を前提とする
``status="proposed"`` の :class:`~core.models.organization.ImprovementProposal`
（``category="new_business"`` / ``target_kind="org_structure"``）として起票する。

設計方針（``trend_to_jobs.convert_trends`` と統一）:
- **自動採用しない**。生成物は承認インボックス（``/api/inbox``）に並ぶ提案で、人間が承認して
  初めて会社（Organization）化へ進む（``requires_human_gate``）。
- **冪等**。trend hash を ``biz:`` プレフィックスで処理済み記録し、提案側は ``dedupe_key`` で
  重複判定する。再実行・部分失敗で二重起票しない。
- ``TrendItem.score`` は 0..10 スケール、純粋関数は 0..1 スケールを想定するため、
  本モジュールが ``score / 10`` で橋渡しする（business_proposal の docstring が指摘する差異の吸収点）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import NAMESPACE_URL, uuid5

from core.trends.business_proposal import (
    TREND_SCORE_SCALE,
    is_business_worthy,
    trend_to_business_proposal,
)
from core.trends.models import TrendItem
from core.trends.store import TrendStore
from core.trends.trend_to_jobs import (
    DEFAULT_MAX_PER_RUN,
    DEFAULT_MIN_SCORE,
    _existing_dedupe_keys,
    _load_processed,
    _resolve_target_org,
    _save_processed,
)

logger = logging.getLogger(__name__)

# 安定 review_id 用の名前空間（trend_to_jobs と同じ思想で、dedupe_key 毎に決定論的 UUID を作る）。
_BIZ_NS = uuid5(NAMESPACE_URL, "pantheon.trends.business")

# TrendStore(0..10) → business_proposal(0..1) への換算係数（単一ソースを参照・P23）。
_SCORE_SCALE = TREND_SCORE_SCALE


def _trend_to_dict(trend: TrendItem) -> Dict[str, Any]:
    """``TrendItem``（score 0..10）を business_proposal が期待する dict（score 0..1）へ橋渡しする。"""
    return {
        "title": trend.title or "",
        "score": (trend.score or 0.0) / _SCORE_SCALE,
        "genre": trend.genre or "",
        "summary": trend.summary or "",
        "url": trend.url or "",
    }


def _proposal_for(trend: TrendItem, payload: Dict[str, Any]):
    """新会社設計ペイロードを承認待ち ImprovementProposal へ変換する。"""
    from core.models.organization import ImprovementProposal

    name = str(payload.get("name") or payload.get("genre") or "新規事業")
    divisions = payload.get("suggested_divisions") or []
    description = (
        f"高スコアトレンド（{trend.score:.1f}）を起点とする新規収益モデル会社の設計案。\n\n"
        f"ジャンル: {payload.get('genre', '(未分類)')}\n"
        f"推奨事業部: {', '.join(divisions) if divisions else '(なし)'}\n"
        f"出典トレンド: {payload.get('source_trend', trend.title)}\n"
        f"URL: {trend.url}\n"
        f"根拠: {payload.get('rationale', '')}\n\n"
        "承認した場合は会社プラグイン／`org create` 相当で Organization を起動する想定。"
    )
    dedupe_key = f"biz:{trend.hash}"
    return ImprovementProposal(
        review_id=uuid5(_BIZ_NS, dedupe_key),
        priority="high" if trend.score >= 8.5 else "medium",
        category="new_business",
        title=f"[新規会社候補] {name}"[:120],
        description=description,
        expected_impact=f"新収益モデル会社の立ち上げ候補 / trend-score {trend.score:.1f}",
        status="proposed",  # 人手承認ゲート（自動採用しない）
        is_meta=True,  # file_path 無しの meta 提案
        dedupe_key=dedupe_key,
        target_kind="org_structure",
        source_org_name="TrendIntelligence",
    )


def scan_business_proposals(
    *,
    platform_home=None,
    min_score: float = DEFAULT_MIN_SCORE,
    max_per_run: int = DEFAULT_MAX_PER_RUN,
    org_name: Optional[str] = None,
) -> Dict[str, Any]:
    """未処理の高スコアトレンドを「新規会社候補」提案へ変換する（承認ゲート経由）。

    冪等: trend hash を ``biz:`` プレフィックスで処理済み記録し、提案は ``dedupe_key`` で
    重複判定する。閾値 ``min_score``（0..10 スケール）未満や ``is_business_worthy`` を満たさない
    トレンドは提案化しない。

    Returns: ``{"proposals": int, "skipped": int, "scanned": int}``
    （受け手 org が無い場合は ``{"proposals": 0, "reason": "no_org"}``）。
    """
    if platform_home is None:
        from core.platform.state import get_platform_home

        platform_home = get_platform_home()

    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home)
    org = _resolve_target_org(psm, org_name)
    if org is None:
        return {"proposals": 0, "reason": "no_org"}

    processed = _load_processed(platform_home)
    store = TrendStore(platform_home)
    candidates: List[TrendItem] = [
        t for t in store.list(limit=200, min_score=min_score) if f"biz:{t.hash}" not in processed
    ]

    sm = psm.get_org_state_manager(org)
    existing_dedupe = _existing_dedupe_keys(sm)
    threshold = float(min_score) / _SCORE_SCALE  # 0..1 スケールの business 閾値

    made = 0
    for trend in candidates[:max_per_run]:
        marker = f"biz:{trend.hash}"
        if not is_business_worthy(_trend_to_dict(trend), min_score=threshold):
            # 閾値未満は提案化しないが、再走査でも判定が変わらないので処理済みに記録する。
            processed.add(marker)
            continue
        if marker in existing_dedupe:  # 既存提案と重複しない（再生成耐性）
            processed.add(marker)
            continue
        try:
            payload = trend_to_business_proposal(_trend_to_dict(trend))
            sm.save_improvement_proposal(_proposal_for(trend, payload))
            existing_dedupe.add(marker)
            processed.add(marker)
            made += 1
        except ValueError:
            # business-worthy 判定を通っていれば通常起きないが、念のため安全弁。
            processed.add(marker)
        except Exception as exc:  # noqa: BLE001
            logger.info("business proposal creation failed for %s: %s", trend.hash, exc)

    _save_processed(platform_home, processed)
    return {
        "proposals": made,
        "skipped": max(0, len(candidates) - max_per_run),
        "scanned": len(candidates),
    }
