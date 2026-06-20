"""P4.2: トレンドから「未開拓ジャンル」を発見し新会社候補を承認ゲートで提案する。

P2.1（トレンド→新規事業提案）の発展形。``TrendStore`` のジャンルのうち、まだ Organization が
存在しない（=未開拓）高スコアジャンルを **決定論・LLM 非依存の集合演算** で抽出し、各ジャンルにつき
1 社の新会社候補を ``status="proposed"`` の :class:`~core.models.organization.ImprovementProposal`
（``category="new_business"`` / ``target_kind="org_structure"``）として起票する。

設計（``business_pipeline.scan_business_proposals`` と統一）:
- 発見はジャンル集合の差分（store のジャンル − 既存 org の industry_genre）。LLM は使わない。
- 提案本体は既存純粋関数 :func:`core.trends.business_proposal.trend_to_business_proposal` を再利用。
- **冪等の単位は「ジャンル」**（1 ジャンル=1 社）。dedupe_key=``untapped:<genre>``・processed マーカも同じ。
  既存 ``business_pipeline`` は trend.hash 単位だが、本モジュールはジャンル単位である点に注意。
- ジャンル正規化は ``business_proposal._slugify`` を store 側・org 側の双方に適用して突合する
  （'Cooking' と 'cooking' の取りこぼし防止）。``industry_genre`` の既定 'general' は被覆扱いしない。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import NAMESPACE_URL, uuid5

from core.trends.business_pipeline import _trend_to_dict
from core.trends.business_proposal import (
    TREND_SCORE_SCALE,
    _slugify,
    is_business_worthy,
    trend_to_business_proposal,
)
from core.trends.store import TrendStore
from core.trends.trend_to_jobs import (
    _existing_dedupe_keys,
    _load_processed,
    _resolve_target_org,
    _save_processed,
)

logger = logging.getLogger(__name__)

# 安定 review_id 用の名前空間。
_NS = uuid5(NAMESPACE_URL, "pantheon.trends.untapped")

# industry_genre の既定値（被覆ジャンルとして数えない）。
_DEFAULT_GENRE = "general"


def enumerate_genre_evidence(
    store: TrendStore, *, min_score: float = 7.0, limit: int = 500
) -> Dict[str, Dict[str, Any]]:
    """store の高スコアトレンドをジャンル（slug）別に集計する（純粋・決定論）。

    Returns: ``{slug_genre: {"count": int, "max_score": float, "top_trend": TrendItem}}``。
    空ジャンルはスキップ。同点は先に出現したトレンドを top に保つ。
    """
    evidence: Dict[str, Dict[str, Any]] = {}
    for trend in store.list(limit=limit, min_score=min_score):
        genre = _slugify(trend.genre or "")
        if not genre or genre == "general":
            # genre 無しは title から推定された 'general' になり区別不能なためスキップ。
            continue
        score = float(trend.score or 0.0)
        cur = evidence.get(genre)
        if cur is None:
            evidence[genre] = {"count": 1, "max_score": score, "top_trend": trend}
        else:
            cur["count"] += 1
            if score > cur["max_score"]:
                cur["max_score"] = score
                cur["top_trend"] = trend
    return evidence


def find_untapped_genres(
    genre_evidence: Dict[str, Dict[str, Any]],
    covered: set[str],
    *,
    min_evidence: int = 1,
    min_score: float = 7.0,
) -> List[str]:
    """被覆ジャンルを除き、事業化に値する未開拓ジャンルを返す（純粋・決定論）。

    - covered は呼び出し側で slug 化済み（既定 'general' は含めない）想定。
    - 各ジャンルは top trend が ``is_business_worthy`` を満たし、かつ証拠件数 >= ``min_evidence``。
      ``min_score``（0..10 スケール）を ``business_pipeline`` と同様 0..1 へ橋渡しして閾値に使う
      （固定 0.6 floor で呼び出し側の min_score を無視しないため）。
    - 並びは (max_score 降順, genre 昇順) で決定論的。
    """
    threshold = float(min_score) / TREND_SCORE_SCALE  # 換算係数の単一ソース（P23）
    result: List[str] = []
    for genre, ev in genre_evidence.items():
        if genre in covered:
            continue
        if int(ev.get("count", 0)) < int(min_evidence):
            continue
        if not is_business_worthy(_trend_to_dict(ev["top_trend"]), min_score=threshold):
            continue
        result.append(genre)
    result.sort(key=lambda g: (-float(genre_evidence[g]["max_score"]), g))
    return result


def _proposal_for_genre(genre: str, evidence: Dict[str, Any], payload: Dict[str, Any]):
    """未開拓ジャンルを承認待ち ImprovementProposal へ変換する。"""
    from core.models.organization import ImprovementProposal

    max_score = float(evidence.get("max_score", 0.0))
    count = int(evidence.get("count", 0))
    top = evidence.get("top_trend")
    divisions = payload.get("suggested_divisions") or []
    dedupe_key = f"untapped:{genre}"
    description = (
        f"未開拓ジャンル『{genre}』をトレンドから検出（証拠 {count} 件・最高スコア {max_score:.1f}）。\n\n"
        f"推奨事業部: {', '.join(divisions) if divisions else '(なし)'}\n"
        f"代表トレンド: {getattr(top, 'title', '')}\n"
        f"URL: {getattr(top, 'url', '')}\n\n"
        "承認すると `pantheon org create --genre <genre>` 相当で新会社を起動する想定。"
    )
    return ImprovementProposal(
        review_id=uuid5(_NS, dedupe_key),
        priority="high" if max_score >= 8.5 else "medium",
        category="new_business",
        title=f"[未開拓ジャンル] {genre}"[:120],
        description=description,
        expected_impact=f"未開拓ジャンル {genre} の新会社立ち上げ候補 / 最高スコア {max_score:.1f}",
        status="proposed",  # 人手承認ゲート
        is_meta=True,
        dedupe_key=dedupe_key,
        target_kind="org_structure",
        source_org_name="TrendIntelligence",
    )


def _covered_genres(psm) -> set[str]:
    """既存 org の industry_genre（slug 化）の集合。既定 'general' は除外する。"""
    covered = {_slugify(o.industry_genre or "") for o in psm.load_organizations()}
    covered.discard(_DEFAULT_GENRE)
    covered.discard("")
    return covered


def scan_untapped_genre_proposals(
    *,
    platform_home=None,
    min_score: float = 7.0,
    min_evidence: int = 1,
    max_per_run: int = 5,
    org_name: Optional[str] = None,
) -> Dict[str, Any]:
    """未開拓ジャンルを発見し新会社候補提案を承認ゲートで起票する（冪等・LLM 非依存）。

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

    store = TrendStore(platform_home)
    evidence = enumerate_genre_evidence(store, min_score=min_score)
    covered = _covered_genres(psm)
    untapped = find_untapped_genres(
        evidence, covered, min_evidence=min_evidence, min_score=min_score
    )

    processed = _load_processed(platform_home)
    sm = psm.get_org_state_manager(org)
    existing = _existing_dedupe_keys(sm)

    made = 0
    for genre in untapped[:max_per_run]:
        marker = f"untapped:{genre}"
        if marker in processed or marker in existing:
            processed.add(marker)
            continue
        try:
            payload = trend_to_business_proposal(_trend_to_dict(evidence[genre]["top_trend"]))
            sm.save_improvement_proposal(_proposal_for_genre(genre, evidence[genre], payload))
            existing.add(marker)
            processed.add(marker)
            made += 1
        except ValueError:
            # is_business_worthy を通過していれば通常起きないが、安全弁。
            processed.add(marker)
        except Exception as exc:  # noqa: BLE001
            logger.info("untapped genre proposal failed for %s: %s", genre, exc)

    _save_processed(platform_home, processed)
    return {
        "proposals": made,
        "skipped": max(0, len(untapped) - max_per_run),
        "scanned": len(untapped),
    }
