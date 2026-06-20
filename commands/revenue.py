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


async def cmd_revenue_projection(args: argparse.Namespace) -> None:
    """月次目標への到達射影（現トレンドで何か月か）を表示する。"""
    from core.metrics.revenue_intelligence import project_to_target

    proj = project_to_target(_revenue_by_month(), args.target)
    print("\n収益プロジェクション（現トレンドの外挿・概算）\n")
    print(f"  目標(月次)  : {proj['target']:,.0f} 円")
    print(f"  直近月収益  : {proj['current']:,.0f} 円")
    print(f"  月次トレンド: {proj['slope_per_month']:+,.0f} 円/月")
    if proj["months_to_target"] == 0:
        print("  到達状況    : ✅ 既に目標到達")
    elif proj["months_to_target"] is None:
        print("  到達状況    : ⚠️ 現トレンドでは到達見込みなし（トレンドが横ばい/下降）")
    else:
        print(f"  到達状況    : 📈 現ペースで約 {proj['months_to_target']} か月後に到達見込み")
    print(f"  3か月後予測 : {proj['projected_3mo']:,.0f} 円")


async def cmd_revenue_forecast(args: argparse.Namespace) -> None:
    """OLS 回帰で多か月の収益予測を表示する（slope/R²/予測系列）。"""
    from core.metrics.revenue_intelligence import analyze_revenue_extended

    horizon = max(1, min(int(args.months), 36))
    a = analyze_revenue_extended(_revenue_by_month(), horizon=horizon)
    if not a["series"]:
        print("[revenue] 収益記録がありません（pantheon revenue collect / hq outcomes record）")
        return
    print(f"\n多か月収益予測（OLS 回帰・{horizon} か月先まで）\n")
    print(
        f"  月次トレンド: {a['slope_per_month']:+,.0f} 円/月  当てはまり(R²): {a['r_squared']:.2f}"
    )
    print(f"  トレンド    : {a['trend']}")
    print("  予測:")
    for i, v in enumerate(a["forecast"], start=1):
        print(f"    +{i:>2}か月後: {v:,.0f} 円")


async def cmd_revenue_attribution(args: argparse.Namespace) -> None:
    """収益をチャネル（source）別に内訳表示する（どの導線が収益を生んでいるか）。"""
    from core.metrics.outcomes import OutcomeStore

    by_channel = OutcomeStore().revenue_by_channel(getattr(args, "org", None) or None)
    total = sum(by_channel.values())
    if not by_channel:
        print("[revenue] 収益記録がありません（source 別の内訳はまだありません）")
        return
    print("\n収益チャネル別アトリビューション\n")
    print(f"  {'チャネル':<16}{'収益(円)':>14}{'比率':>8}")
    for ch, amount in by_channel.items():
        pct = (amount / total * 100) if total else 0.0
        print(f"  {ch:<16}{amount:>14,.0f}{pct:>7.1f}%")
    print(f"\n  合計: {total:,.0f} 円")


async def cmd_revenue_goal_status(args: argparse.Namespace) -> None:
    """月次目標への到達状況と backpressure（未達の圧）を表示する。"""
    from core.metrics.revenue_intelligence import compute_goal_status

    s = compute_goal_status(_revenue_by_month(), args.target)
    label = {
        "on_track": "✅ 順調（予測が目標以上）",
        "mild": "🟡 やや未達",
        "strong": "🔴 大きく未達（要構造介入）",
    }
    print("\n収益ゴールステータス\n")
    print(f"  目標(月次)  : {s['target']:,.0f} 円  到達率: {s['attainment_pct']:.0f}%")
    print(f"  直近月収益  : {s['current']:,.0f} 円  翌月予測: {s['forecast_next']:,.0f} 円")
    print(f"  予測ギャップ: {s['forecast_gap']:,.0f} 円")
    print(f"  backpressure: {label.get(s['backpressure_level'], s['backpressure_level'])}")
    if s["months_to_target"] == 0:
        print("  到達見込み  : 既に到達")
    elif s["months_to_target"] is None:
        print("  到達見込み  : 現トレンドでは到達見込みなし")
    else:
        print(f"  到達見込み  : 約 {s['months_to_target']} か月後")


async def cmd_revenue_integrity(args: argparse.Namespace) -> None:
    """確定収益（記録済み実データのみ）とデータ整合性を表示する（予測は含めない）。"""
    from core.metrics.outcomes import OutcomeStore
    from core.metrics.revenue_integrity import assess_revenue_integrity

    integ = assess_revenue_integrity(OutcomeStore(), getattr(args, "org", None) or None)
    print("\n収益データ整合性（確定＝記録済み実イベントのみ）\n")
    print(f"  確定収益    : {integ['confirmed_revenue']:,.0f} 円")
    print(f"  実イベント数: {integ['recorded_event_count']} 件")
    print(f"  確認チャネル: {', '.join(integ['confirmed_sources']) or '(なし)'}")
    if integ["warning"]:
        print(f"\n  ⚠️ {integ['warning']}")
    else:
        print("\n  ✅ 確定収益データあり。予測・見通しは別途『概算』として扱われます。")


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("revenue", help="収益の自動収集・レポート・分析")
    sub = parser.add_subparsers(dest="revenue_command", required=True)

    sp = sub.add_parser("collect", help="note/X/ASP から収益を自動収集（未接続は接続タスクを起票）")
    sp.set_defaults(handler_name="cmd_revenue_collect")

    sp = sub.add_parser("report", help="月次収益レポート（前月比つき）を表示")
    sp.set_defaults(handler_name="cmd_revenue_report")

    sp = sub.add_parser("intelligence", help="収益トレンド・翌月予測を表示（analyze_revenue）")
    sp.set_defaults(handler_name="cmd_revenue_intelligence")

    sp = sub.add_parser("projection", help="月次目標への到達射影（現トレンドで何か月か）")
    sp.add_argument("--target", type=float, required=True, help="月次収益目標（円）")
    sp.set_defaults(handler_name="cmd_revenue_projection")

    sp = sub.add_parser("forecast", help="OLS 回帰で多か月の収益予測（slope/R²/予測系列）")
    sp.add_argument("--months", type=int, default=12, help="予測する月数（既定 12・最大 36）")
    sp.set_defaults(handler_name="cmd_revenue_forecast")

    sp = sub.add_parser("attribution", help="収益をチャネル（source）別に内訳表示")
    sp.add_argument("--org", default=None, help="対象 Organization（省略で全 org 横断）")
    sp.set_defaults(handler_name="cmd_revenue_attribution")

    sp = sub.add_parser("goal-status", help="月次目標への到達状況と backpressure（未達の圧）")
    sp.add_argument("--target", type=float, required=True, help="月次収益目標（円）")
    sp.set_defaults(handler_name="cmd_revenue_goal_status")

    sp = sub.add_parser("integrity", help="確定収益（記録済み実データのみ）とデータ整合性を表示")
    sp.add_argument("--org", default=None, help="対象 Organization（省略で全 org 横断）")
    sp.set_defaults(handler_name="cmd_revenue_integrity")
