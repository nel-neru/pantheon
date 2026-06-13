"""P4.1: 「月XX円目標で最適運用して」→ 計画 → 承認ゲート提案（完全自律経営デモ）。

自然言語ゴール（収益目標額）を起点に、**決定論・LLM 非依存**で
「現ポートフォリオの成果（OutcomeStore）→ 目標とのギャップ → 優先度付きの打ち手群」を生成し、
人手承認を前提とする ``status="proposed"`` の :class:`~core.models.organization.ImprovementProposal`
として承認インボックスへ積む。

設計（``core.trends.business_pipeline.scan_business_proposals`` と統一）:
- **新規ロジックはほぼ無い**。計画は既存の純粋コア
  :func:`core.hierarchy.portfolio_advisor.build_portfolio_proposals`（配分＋送客）に委譲し、
  ギャップ計算（目標 vs 直近実績/予測）と「ギャップ符号に応じた強調並べ替え」だけが新規。
- **claude CLI を一切呼ばない**（``goal run`` の LLM 経路とは別物）。テストはオフラインで完結。
- **冪等**。dedupe_key は収益値に依存しない安定キー（org_name+action / from→to / 目標額）にし、
  実績が変わって再実行しても重複起票しない。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import NAMESPACE_URL, uuid5

from core.hierarchy.portfolio_advisor import build_portfolio_proposals
from core.metrics.revenue_intelligence import analyze_revenue
from core.trends.trend_to_jobs import _existing_dedupe_keys, _resolve_target_org

logger = logging.getLogger(__name__)

# 安定 review_id 用の名前空間（business_pipeline._BIZ_NS と同じ思想）。
_NS = uuid5(NAMESPACE_URL, "pantheon.hierarchy.portfolio")

# ギャップ未達（under target）時の「収益に近い打ち手」を上位へ寄せる強調順位。
# 既存リーチを今すぐ収益化（monetize/送客）> 伸ばす（invest）> 新規事業 > 最適化/読者獲得。
_UNDER_TARGET_EMPHASIS: Dict[str, int] = {
    "monetize": 5,
    "invest": 3,
    "optimize": 1,
    "grow_audience": 0,
}

# proposal の category（inbox の収益インパクト並べ替えが既に解釈するキーに合わせる）。
_KIND_TO_CATEGORY = {
    "portfolio_allocation": "portfolio_allocation",
    "handoff": "cross_org_handoff",
    "new_business": "new_business",
}


def compute_revenue_gap(target: float, by_month: Dict[str, float]) -> Dict[str, Any]:
    """目標額と月次収益から、現状/予測とのギャップを計算する（純粋・冪等・LLM 非依存）。

    - current: 直近の実月の収益（月次ランレート）。実月が無ければ 0。
    - lifetime: 全バケットの合計（通算収益）。
    - forecast: ``analyze_revenue`` の翌月予測。
    - present_gap / forecast_gap: 目標 − 現状 / 目標 − 予測。
    - under_target: present_gap > 0（目標未達）。
    """
    months = sorted(m for m in by_month if m != "unknown" and len(m) == 7 and m[4] == "-")
    current = float(by_month[months[-1]]) if months else 0.0
    lifetime = float(sum(float(v) for v in by_month.values()))  # 空入力でも float を保つ
    forecast = float(analyze_revenue(by_month)["forecast_next"])
    target = float(target)
    present_gap = target - current
    return {
        "target": target,
        "current": current,
        "lifetime": lifetime,
        "forecast": forecast,
        "present_gap": present_gap,
        "forecast_gap": target - forecast,
        "under_target": present_gap > 0,
    }


def _entry_emphasis(entry: Dict[str, Any]) -> int:
    """計画エントリの「収益に近い度」（under target 時の強調並べ替え用）。"""
    kind = entry.get("kind")
    if kind == "handoff":
        return 4
    if kind == "new_business":
        return 2
    return _UNDER_TARGET_EMPHASIS.get(str(entry.get("action", "")), 0)


def build_target_plan(
    target: float,
    org_stats: List[Dict[str, Any]],
    gap: Dict[str, Any],
    *,
    source_org_name: str = "HQ",
    min_reach: float = 0.0,
) -> List[Dict[str, Any]]:
    """目標額に向けた打ち手群（計画エントリの dict リスト）を組む（純粋・決定論・冪等）。

    既存の ``build_portfolio_proposals``（配分＋送客）を計画の土台にし、目標未達なら
    収益に近い打ち手を上位へ強調並べ替え。さらに「予測でも目標に届かず、かつ総リーチが
    ``min_reach`` 以下」のときは新規収益源（new_business）の立ち上げ提案を追加する
    （配分だけでは到達不能なケースで「何もしない計画」を避ける）。
    """
    plan = build_portfolio_proposals(org_stats, source_org_name=source_org_name)
    if gap.get("under_target"):
        plan = sorted(plan, key=lambda e: (-_entry_emphasis(e), str(e.get("title", ""))))

    total_reach = sum(float(s.get("reach", 0.0) or 0.0) for s in org_stats)
    if gap.get("forecast_gap", 0.0) > 0 and total_reach <= float(min_reach):
        plan.append(
            {
                "kind": "new_business",
                "title": f"[HQ提案] 新規収益源を立ち上げ（月{int(target)}円目標にリーチ不足）",
                "reason": (
                    f"総リーチ {int(total_reach)} では予測でも目標 {int(target)} 円に届かないため、"
                    "新規事業（会社プラグイン/未開拓ジャンル）の立ち上げを検討する。"
                ),
                "priority": 2,
                "source_org_name": source_org_name,
            }
        )
    return plan


def _priority_str(value: Any) -> str:
    """計画エントリの int priority を ImprovementProposal の {high,medium,low} へ写像する。"""
    try:
        p = int(float(value))
    except (TypeError, ValueError):
        p = 0
    if p >= 2:
        return "high"
    if p == 1:
        return "medium"
    return "low"


def _dedupe_key_for(entry: Dict[str, Any], *, target: float) -> str:
    """収益値に依存しない安定 dedupe_key（再実行で重複起票しない）。

    重要: ``action``（monetize/invest/...）や送客先 ``to_org`` は収益実績で変わるため
    **キーに含めない**（recommend_handoffs は最高収益の monetizer を to_org に選ぶので、
    実績の上下で送客先が入れ替わる）。配分は org 当たり 1 件、送客は送客元（from_org）当たり
    1 件に固定し、実績変動で重複起票しないようにする（action/to_org は title に残す）。
    """
    kind = entry.get("kind")
    if kind == "portfolio_allocation":
        return f"portfolio:alloc:{entry.get('org_name', '')}"
    if kind == "handoff":
        # recommend_handoffs は from_org 当たり最大 1 件。to_org は実績で変わるため含めない。
        return f"portfolio:handoff:{entry.get('from_org', '')}"
    if kind == "new_business":
        return f"portfolio:newbiz:{int(float(target))}"
    return f"portfolio:{kind}:{entry.get('title', '')}"


def _proposal_for_entry(entry: Dict[str, Any], *, target: float, source_org_name: str):
    """計画エントリを承認待ち ImprovementProposal へ変換する（business_pipeline._proposal_for に倣う）。"""
    from core.models.organization import ImprovementProposal

    kind = str(entry.get("kind") or "")
    category = _KIND_TO_CATEGORY.get(kind, "portfolio_allocation")
    dedupe_key = _dedupe_key_for(entry, target=target)
    title = str(entry.get("title") or "[HQ提案] ポートフォリオ最適化")[:120]
    description = (
        f"月{int(float(target))}円目標に向けた自律運用プランの 1 手。\n\n"
        f"打ち手: {kind}\n"
        f"理由: {entry.get('reason', '')}\n\n"
        "承認するとこの施策を実行（配分変更/送客/新規事業の起票）へ進む（人手承認ゲート）。"
    )
    return ImprovementProposal(
        review_id=uuid5(_NS, dedupe_key),
        priority=_priority_str(entry.get("priority")),
        category=category,
        title=title,
        description=description,
        expected_impact=f"月{int(float(target))}円目標へのポートフォリオ最適化",
        status="proposed",  # 人手承認ゲート
        is_meta=True,
        dedupe_key=dedupe_key,
        target_kind="org_structure",
        source_org_name=source_org_name,
    )


def _gather_org_stats(psm, store) -> List[Dict[str, Any]]:
    """非システム org の {org_name, revenue, reach, posts} を集計する（/api/hq/portfolio と同形）。"""
    stats: List[Dict[str, Any]] = []
    for org in psm.load_organizations():
        if org.is_system:
            continue
        summary = store.summary_for_org(org.name)
        stats.append(
            {
                "org_name": org.name,
                "revenue": summary.total_revenue,
                "reach": summary.total_reach,
                "posts": summary.by_metric.get("posts", {}).get("sum", 0.0),
            }
        )
    return stats


def preview_portfolio_plan(
    *,
    target: float,
    platform_home=None,
    source_org_name: str = "HQ",
    min_reach: float = 0.0,
) -> Dict[str, Any]:
    """目標額に対するギャップと計画を返す（**起票しない** プレビュー・GUI/CLI 用）。"""
    if platform_home is None:
        from core.platform.state import get_platform_home

        platform_home = get_platform_home()

    from core.metrics.outcomes import OutcomeStore
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home)
    store = OutcomeStore(platform_home=platform_home)
    org_stats = _gather_org_stats(psm, store)
    gap = compute_revenue_gap(target, store.revenue_by_month(None))
    plan = build_target_plan(
        target, org_stats, gap, source_org_name=source_org_name, min_reach=min_reach
    )
    return {"gap": gap, "plan": plan}


def scan_portfolio_proposals(
    *,
    target: float,
    platform_home=None,
    source_org_name: str = "HQ",
    org_name: Optional[str] = None,
    min_reach: float = 0.0,
) -> Dict[str, Any]:
    """目標額の計画を承認ゲート提案として起票する（冪等・LLM 非依存・自動採用しない）。

    Returns: ``{"proposals": int, "skipped": int, "scanned": int}``
    （受け手 org が無い場合は ``{"proposals": 0, "reason": "no_org"}``）。
    """
    if platform_home is None:
        from core.platform.state import get_platform_home

        platform_home = get_platform_home()

    from core.metrics.outcomes import OutcomeStore
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home)
    org = _resolve_target_org(psm, org_name)
    if org is None:
        return {"proposals": 0, "reason": "no_org"}

    store = OutcomeStore(platform_home=platform_home)
    org_stats = _gather_org_stats(psm, store)
    gap = compute_revenue_gap(target, store.revenue_by_month(None))
    plan = build_target_plan(
        target, org_stats, gap, source_org_name=source_org_name, min_reach=min_reach
    )

    sm = psm.get_org_state_manager(org)
    existing = _existing_dedupe_keys(sm)
    made = 0
    for entry in plan:
        proposal = _proposal_for_entry(entry, target=target, source_org_name=source_org_name)
        if proposal.dedupe_key in existing:
            continue
        try:
            sm.save_improvement_proposal(proposal)
            existing.add(proposal.dedupe_key)
            made += 1
        except Exception as exc:  # noqa: BLE001
            logger.info("portfolio proposal creation failed for %s: %s", proposal.dedupe_key, exc)

    return {"proposals": made, "skipped": len(plan) - made, "scanned": len(plan)}
