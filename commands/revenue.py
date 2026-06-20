"""`pantheon revenue` — 収益の自動収集（REV-COLLECT）。

`collect` で note/X/ASP アダプタを巡回し、接続済みは収益を OutcomeStore へ記録、
未接続は「接続してください」という人間タスクを承認キューへ積む（実認証は human-gate）。
"""

from __future__ import annotations

import argparse
from typing import Any


async def cmd_revenue_collect(args: argparse.Namespace) -> None:
    """外部プラットフォームから収益を自動収集する（接続済みのみ・未接続は接続タスクを起票）。"""
    from core.metrics.revenue_collectors import run_revenue_collection

    result = run_revenue_collection()
    print(
        f"[revenue] {result['recorded']} 件を記録"
        f"（収集: {', '.join(result['collected_sources']) or 'なし'}）"
    )
    if result["needs_connection"]:
        print(
            "  未接続のため接続タスクを起票: "
            + ", ".join(result["needs_connection"])
            + "（/human-tasks で確認 → revenue_imports/<source>.csv を置くか資格情報を接続すると自動収集）"
        )


def _revenue_by_month() -> dict:
    from core.metrics.outcomes import OutcomeStore

    return OutcomeStore().revenue_by_month(None)


async def cmd_revenue_report(args: argparse.Namespace) -> None:
    """月次収益レポートを表示する（GUI の月次収益レポートと同じデータ・CLI 経路）。"""
    by_month = _revenue_by_month()
    months = sorted(m for m in by_month if m != "unknown" and len(m) == 7 and m[4] == "-")
    if not months:
        print("[revenue] 収益記録がありません（pantheon revenue collect / hq outcomes record）")
        return
    print("\n月次収益レポート\n")
    print(f"  {'月':<9}{'収益(円)':>14}{'前月比':>12}")
    prev: float | None = None
    for m in months:
        cur = float(by_month[m])
        if prev is None or prev == 0:
            delta = "—"
        else:
            delta = f"{(cur - prev) / prev * 100:+.1f}%"
        print(f"  {m:<9}{cur:>14,.0f}{delta:>12}")
        prev = cur
    total = sum(float(by_month[m]) for m in months)
    print(f"\n  合計: {total:,.0f} 円（{len(months)} か月）")


async def cmd_revenue_intelligence(args: argparse.Namespace) -> None:
    """収益トレンド/翌月予測を表示する（GUI のトレンドカードと同じ analyze_revenue・CLI 経路）。"""
    from core.metrics.revenue_intelligence import analyze_revenue

    analysis = analyze_revenue(_revenue_by_month())
    trend_label = {
        "growing": "📈 成長",
        "declining": "📉 逓減",
        "flat": "→ 横ばい",
        "insufficient": "データ不足",
    }.get(analysis["trend"], analysis["trend"])
    print("\n収益インテリジェンス（決定論・LLM 非依存）\n")
    print(f"  トレンド    : {trend_label}")
    latest = analysis["latest_change_pct"]
    print(f"  直近前月比  : {f'{latest:+.1f}%' if latest is not None else '—'}")
    print(f"  翌月予測    : {analysis['forecast_next']:,.0f} 円（概算）")
    print(f"  データ月数  : {len(analysis['months'])}")


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("revenue", help="収益の自動収集・レポート・分析")
    sub = parser.add_subparsers(dest="revenue_command", required=True)

    sp = sub.add_parser("collect", help="note/X/ASP から収益を自動収集（未接続は接続タスクを起票）")
    sp.set_defaults(handler_name="cmd_revenue_collect")

    sp = sub.add_parser("report", help="月次収益レポート（前月比つき）を表示")
    sp.set_defaults(handler_name="cmd_revenue_report")

    sp = sub.add_parser("intelligence", help="収益トレンド・翌月予測を表示（analyze_revenue）")
    sp.set_defaults(handler_name="cmd_revenue_intelligence")
