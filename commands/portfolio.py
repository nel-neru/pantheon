"""`pantheon portfolio` — 統合コマンドセンター（拡張: 全社の意思決定サマリを一望）。

Revenue / Businesses / Proposals / Goals を行き来せずに、全 Organization の ROI・コホート内
percentile・推奨アクション（invest/monetize/optimize/grow_audience）と、保留中の機会
（クロス Org ハンドオフ・新規会社候補）を一画面に集約する読み取り専用ビュー。

既存の純粋コア（recommend_allocation / build_benchmark_snapshot）＋ OutcomeStore を合成するだけで、
新しい意思決定ロジックは導入しない（GUI の /api/portfolio/overview と同じ集約の CLI 版）。
"""

from __future__ import annotations

import argparse
from typing import Any

_FLAG_MARK = {"top_performer": "★", "underperformer": "⚠"}
_ACTION_LABEL = {
    "invest": "投資（伸ばす）",
    "monetize": "収益化",
    "optimize": "効率改善",
    "grow_audience": "集客育成",
}


async def cmd_portfolio_overview(args: argparse.Namespace, *, get_psm: Any) -> None:
    """全 org の ROI/percentile/推奨アクション＋保留機会を一覧表示する。"""
    from core.metrics.benchmarking import build_benchmark_snapshot
    from core.metrics.outcomes import OutcomeStore
    from core.metrics.portfolio import recommend_allocation

    psm = get_psm()
    store = OutcomeStore(platform_home=psm.platform_home)
    org_stats = []
    for org in psm.load_organizations():
        if getattr(org, "is_system", False):
            continue
        summary = store.summary_for_org(org.name)
        org_stats.append(
            {
                "org_name": org.name,
                "revenue": summary.total_revenue,
                "reach": summary.total_reach,
            }
        )
    if not org_stats:
        print(
            "対象 Organization がありません（pantheon org add / plugin install-company で作成）。"
        )
        return

    alloc = {a["org_name"]: a for a in recommend_allocation(org_stats)}
    bench = build_benchmark_snapshot(org_stats)

    total_rev = sum(s["revenue"] for s in org_stats)
    total_reach = sum(s["reach"] for s in org_stats)
    print("\n━━ ポートフォリオ・コマンドセンター ━━")
    print(f"  会社 {len(org_stats)} 社  収益計 {total_rev:,.0f} 円  リーチ計 {total_reach:,.0f}\n")
    print(f"  {'会社':<20}{'ROI':>8}{'収益%':>7}  推奨アクション")
    for b in bench:  # 収益降順
        a = alloc.get(b["org_name"], {})
        mark = _FLAG_MARK.get(b["flag"], " ")
        action = _ACTION_LABEL.get(a.get("action", ""), a.get("action", "-"))
        print(
            f"  {mark}{b['org_name']:<19}{b['roi']:>8.3f}{b['revenue_percentile']:>6.0f}%  {action}"
        )

    # 保留中の機会（actuate 候補）。
    from core.hierarchy.org_handoff import HANDOFF_PENDING, OrgHandoffStore

    pending_handoffs = len(
        OrgHandoffStore(platform_home=psm.platform_home).list_handoffs(status=HANDOFF_PENDING)
    )
    new_biz = 0
    for org in psm.load_organizations():
        try:
            sm = psm.get_org_state_manager(org)
            new_biz += sum(
                1
                for p in sm.get_pending_improvement_proposals(limit=50)
                if p.get("category") == "new_business"
            )
        except Exception:  # noqa: BLE001
            continue
    print(f"\n  保留中の機会: 承認待ちハンドオフ {pending_handoffs} 件 / 新規会社候補 {new_biz} 件")
    print("  次の一手: pantheon inbox list --sort roi（高 ROI から処理）")


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("portfolio", help="統合コマンドセンター（全社の意思決定サマリ）")
    sub = parser.add_subparsers(dest="portfolio_command", required=True)

    ov = sub.add_parser("overview", help="全 org の ROI/percentile/推奨アクション＋保留機会を一覧")
    ov.set_defaults(handler_name="cmd_portfolio_overview")
