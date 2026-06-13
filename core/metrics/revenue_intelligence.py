"""Revenue Intelligence — 収益の月次系列から成長率・トレンド・簡易フォーキャストを導く。

`OutcomeStore.revenue_by_month` が返す ``{YYYY-MM: 合計}`` を入力に、前月比（MoM）・
直近トレンド（成長/横ばい/逓減）・翌月予測を **決定論的**（LLM なし）に計算する。
Phase 1「収益ループ完成」の分析層: 収益データを意思決定材料へ変換する第一歩。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

# 直近トレンド判定のしきい値（平均 MoM がこの割合を超えれば成長/下回れば逓減）。
TREND_THRESHOLD = 0.05  # ±5%
# トレンド/予測に使う直近の MoM 期間数。
RECENT_WINDOW = 3


class RevenueAnalysis(TypedDict):
    months: List[str]
    series: List[float]
    mom_change_pct: List[Optional[float]]
    latest_change_pct: Optional[float]
    trend: str  # "growing" | "flat" | "declining" | "insufficient"
    forecast_next: float


def _real_months(by_month: Dict[str, float]) -> List[str]:
    """``unknown`` バケットを除いた実月キーを昇順で返す。"""
    return sorted(m for m in by_month if m != "unknown" and len(m) == 7 and m[4] == "-")


def analyze_revenue(by_month: Dict[str, float]) -> RevenueAnalysis:
    """月次収益から MoM・トレンド・翌月予測を計算する（純粋関数・冪等）。

    - mom_change_pct: 各月の前月比（%）。前月が 0 の月は None（割れない）。
    - trend: 直近 ``RECENT_WINDOW`` の平均 MoM がしきい値で成長/横ばい/逓減。2点未満は insufficient。
    - forecast_next: 直近平均成長率を最終月に適用（計算不能なら最終月の値を据え置き）。
    """
    months = _real_months(by_month)
    series = [float(by_month[m]) for m in months]

    if len(series) < 2:
        return RevenueAnalysis(
            months=months,
            series=series,
            mom_change_pct=[],
            latest_change_pct=None,
            trend="insufficient",
            forecast_next=series[-1] if series else 0.0,
        )

    mom_pct: List[Optional[float]] = []
    mom_frac: List[float] = []  # 予測/トレンド用（割れた月のみ）
    for prev, cur in zip(series, series[1:]):
        if prev == 0:
            mom_pct.append(None)
            continue
        frac = (cur - prev) / prev
        mom_pct.append(round(frac * 100, 1))
        mom_frac.append(frac)

    latest_change_pct = mom_pct[-1] if mom_pct else None

    recent = mom_frac[-RECENT_WINDOW:] if mom_frac else []
    avg_recent = sum(recent) / len(recent) if recent else 0.0
    if not recent:
        trend = "flat"
    elif avg_recent > TREND_THRESHOLD:
        trend = "growing"
    elif avg_recent < -TREND_THRESHOLD:
        trend = "declining"
    else:
        trend = "flat"

    forecast_next = round(series[-1] * (1 + avg_recent), 2)

    return RevenueAnalysis(
        months=months,
        series=series,
        mom_change_pct=mom_pct,
        latest_change_pct=latest_change_pct,
        trend=trend,
        forecast_next=forecast_next,
    )


# 収益インパクトのランク（提案キューの優先順位付け）。
REVENUE_IMPACT_HIGH = 2  # 直接収益化（収益化事業部追加・収益化目標など）
REVENUE_IMPACT_MEDIUM = 1  # 収益に近い（集客/コンテンツ＝リーチ→収益の入口）
REVENUE_IMPACT_NONE = 0

# 収益化に直結する HQ 介入の target_ref / target_category / division type。
_HIGH_TARGET_REFS = {"add_monetization_division", "monetization_from_outcomes"}
_HIGH_CATEGORIES = {"performance", "monetization", "revenue"}
_HIGH_DIVISION_TYPES = {"monetization"}
_MEDIUM_DIVISION_TYPES = {"audience_development", "content_production"}


def revenue_impact_rank(proposal: Dict[str, Any]) -> int:
    """提案の「収益インパクト」を 0/1/2 でランク付けする（提案キューの並び替え用）。

    収益化に直結（収益化事業部の新設・収益化目標）= 2、集客/コンテンツ（リーチ→収益の入口）
    = 1、それ以外 = 0。HQ の収益駆動提案（P1.1）を承認キューの上位へ押し上げる根拠。
    決定論的で、提案 dict の欠損キーにも安全（不明は 0）。
    """
    if not isinstance(proposal, dict):
        return REVENUE_IMPACT_NONE
    target_ref = str(proposal.get("target_ref") or "")
    spec = (
        proposal.get("intervention_spec")
        if isinstance(proposal.get("intervention_spec"), dict)
        else {}
    )
    division = spec.get("division") if isinstance(spec.get("division"), dict) else {}
    div_type = str(division.get("type") or "")
    category = str(spec.get("target_category") or "")

    if (
        target_ref in _HIGH_TARGET_REFS
        or div_type in _HIGH_DIVISION_TYPES
        or category in _HIGH_CATEGORIES
    ):
        return REVENUE_IMPACT_HIGH
    if div_type in _MEDIUM_DIVISION_TYPES or str(proposal.get("category") or "") == "content_asset":
        return REVENUE_IMPACT_MEDIUM
    return REVENUE_IMPACT_NONE
