"""Revenue Intelligence — 収益の月次系列から成長率・トレンド・簡易フォーキャストを導く。

`OutcomeStore.revenue_by_month` が返す ``{YYYY-MM: 合計}`` を入力に、前月比（MoM）・
直近トレンド（成長/横ばい/逓減）・翌月予測を **決定論的**（LLM なし）に計算する。
Phase 1「収益ループ完成」の分析層: 収益データを意思決定材料へ変換する第一歩。
"""

from __future__ import annotations

import statistics
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
    # 翌月予測の概算信頼区間（直近 MoM のばらつきから導く・点推定の信頼度を可視化）。
    forecast_lower: float
    forecast_upper: float


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
        only = series[-1] if series else 0.0
        return RevenueAnalysis(
            months=months,
            series=series,
            mom_change_pct=[],
            latest_change_pct=None,
            trend="insufficient",
            forecast_next=only,
            forecast_lower=only,
            forecast_upper=only,
        )

    mom_pct: List[Optional[float]] = []
    mom_frac: List[float] = []  # 予測/トレンド用（割れた月のみ）
    # 隣接ペア（前月, 当月）を作る意図的な切り捨て：series[1:] は1要素短いのが正しいので
    # strict=False を明示する（strict=True は誤り。B905 を意図どおりに黙らせる）。
    for prev, cur in zip(series, series[1:], strict=False):
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

    last = series[-1]
    forecast_next = round(last * (1 + avg_recent), 2)
    # 直近成長率のばらつき（標準偏差）を予測の不確実性とみなし、概算バンドを作る。
    # 1点しか無ければスプレッド 0（点推定のまま）。収益は負にならないので下限は 0 で丸める。
    spread = statistics.pstdev(recent) if len(recent) >= 2 else 0.0
    forecast_lower = round(max(0.0, last * (1 + avg_recent - spread)), 2)
    forecast_upper = round(last * (1 + avg_recent + spread), 2)

    return RevenueAnalysis(
        months=months,
        series=series,
        mom_change_pct=mom_pct,
        latest_change_pct=latest_change_pct,
        trend=trend,
        forecast_next=forecast_next,
        forecast_lower=forecast_lower,
        forecast_upper=forecast_upper,
    )


class TargetProjection(TypedDict):
    target: float
    current: float  # 直近月の収益
    slope_per_month: float  # 月次の平均増減（最小二乗回帰の傾き）
    on_track: bool  # 現トレンドで到達見込みか
    months_to_target: Optional[int]  # 到達までの月数（到達済み=0 / 到達不能=None）
    projected_3mo: float  # 3か月後の予測収益


class ExtendedRevenueAnalysis(TypedDict):
    months: List[str]
    series: List[float]
    slope_per_month: float  # OLS 回帰の傾き（月あたり平均増減）
    intercept: float
    r_squared: float  # 当てはまりの良さ（0..1, 1=完全線形）
    trend: str
    forecast: List[float]  # 次 horizon か月の予測（下限 0）


def _ols(series: List[float]) -> tuple[float, float, float]:
    """月次系列に最小二乗回帰を当て (slope, intercept, r_squared) を返す（stdlib のみ）。

    2 点未満は (0.0, last|0, 0.0)。分散ゼロ（全点同値）は slope=0/intercept=mean/r2=1.0。
    scipy/numpy 非依存（requirements に無い）で revenue クリティカルパスを再現可能に保つ。
    """
    n = len(series)
    if n == 0:
        return (0.0, 0.0, 0.0)
    if n == 1:
        return (0.0, series[0], 0.0)
    mean_x = (n - 1) / 2.0
    mean_y = sum(series) / n
    ss_xx = sum((i - mean_x) ** 2 for i in range(n))
    ss_xy = sum((i - mean_x) * (series[i] - mean_y) for i in range(n))
    ss_yy = sum((y - mean_y) ** 2 for y in series)
    if ss_xx == 0:
        return (0.0, mean_y, 0.0)
    slope = ss_xy / ss_xx
    intercept = mean_y - slope * mean_x
    # R² = 説明された分散 / 全分散。全点同値（ss_yy=0）は完全当てはめ扱い。
    r_squared = 1.0 if ss_yy == 0 else max(0.0, min(1.0, (ss_xy**2) / (ss_xx * ss_yy)))
    return (slope, intercept, r_squared)


def analyze_revenue_extended(
    by_month: Dict[str, float], horizon: int = 12
) -> ExtendedRevenueAnalysis:
    """月次収益に OLS を当て、``horizon`` か月先までの予測系列を返す（決定論・LLM 非依存）。

    既存 ``analyze_revenue``（1か月先＋信頼バンド）はそのまま残し、これは多か月計画
    （四半期/年）と目標実現性のストレステスト用の上位互換。予測は線形外挿で下限 0。
    """
    months = _real_months(by_month)
    series = [float(by_month[m]) for m in months]
    slope, intercept, r2 = _ols(series)
    n = len(series)
    forecast = [round(max(0.0, slope * (n - 1 + k) + intercept), 2) for k in range(1, horizon + 1)]

    if n < 2:
        trend = "insufficient"
    elif slope > TREND_THRESHOLD * (sum(series) / n or 1):
        trend = "growing"
    elif slope < -TREND_THRESHOLD * (sum(series) / n or 1):
        trend = "declining"
    else:
        trend = "flat"

    return ExtendedRevenueAnalysis(
        months=months,
        series=series,
        slope_per_month=round(slope, 2),
        intercept=round(intercept, 2),
        r_squared=round(r2, 4),
        trend=trend,
        forecast=forecast,
    )


def _linear_slope(series: List[float]) -> float:
    """月次系列の最小二乗回帰の傾き（= 月あたり平均増減）。2点未満は 0.0。

    単月のスパイク/ディップに左右されにくい run-rate トレンドを返す（単純差分より頑健）。
    """
    n = len(series)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(series) / n
    denom = sum((i - mean_x) ** 2 for i in range(n))
    if denom == 0:
        return 0.0
    num = sum((i - mean_x) * (series[i] - mean_y) for i in range(n))
    return num / denom


class GoalStatus(TypedDict):
    target: float
    current: float  # 直近月収益
    forecast_next: float  # 翌月予測（analyze_revenue）
    gap: float  # target - current（現状の不足）
    forecast_gap: float  # target - forecast_next（予測でも残る不足）
    attainment_pct: float  # current / target * 100
    backpressure_level: str  # on_track | mild | strong（目標未達の圧の強さ）
    months_to_target: Optional[int]  # 現トレンドでの到達月数（project_to_target 由来）
    trend: str


# backpressure（目標未達の圧）の閾値: 予測が目標のこの割合を下回ると "strong"。
_BACKPRESSURE_MILD = 1.0  # 予測 >= target なら on_track
_BACKPRESSURE_STRONG = 0.8  # 予測 < target*0.8 なら strong（要構造介入レベル）


def compute_goal_status(by_month: Dict[str, float], target: float) -> GoalStatus:
    """月次目標に対する到達状況と backpressure（未達の圧）を算出する（決定論・LLM 非依存）。

    analyze_revenue（翌月予測）＋ project_to_target（到達月数）を合成し、Revenue Goal Autopilot や
    Dashboard が「目標に対しどれだけ・どの強さで未達か」を一目で判断できる状態を返す。
    backpressure_level: 予測>=target=on_track / 予測>=target*0.8=mild / それ未満=strong。
    """
    analysis = analyze_revenue(by_month)
    current = analysis["series"][-1] if analysis["series"] else 0.0
    forecast_next = float(analysis["forecast_next"])
    tgt = float(target)
    projection = project_to_target(by_month, tgt)

    if tgt <= 0:
        level = "on_track"
    elif forecast_next >= tgt * _BACKPRESSURE_MILD:
        level = "on_track"
    elif forecast_next >= tgt * _BACKPRESSURE_STRONG:
        level = "mild"
    else:
        level = "strong"

    return GoalStatus(
        target=tgt,
        current=current,
        forecast_next=forecast_next,
        gap=round(tgt - current, 2),
        forecast_gap=round(tgt - forecast_next, 2),
        attainment_pct=round(current / tgt * 100, 1) if tgt > 0 else 0.0,
        backpressure_level=level,
        months_to_target=projection["months_to_target"],
        trend=analysis["trend"],
    )


def project_to_target(by_month: Dict[str, float], target: float) -> TargetProjection:
    """月次収益の trajectory から「月次目標 ``target`` に何か月で到達するか」を射影する。

    現トレンド（最小二乗回帰の傾き）を run-rate として外挿する決定論関数（LLM 非依存）。
    - 既に ``current >= target`` → 到達済み（months_to_target=0, on_track=True）。
    - 傾き <= 0 かつ未達 → 現トレンドでは到達不能（months_to_target=None, on_track=False）。
    - それ以外 → ``ceil((target - current) / slope)`` か月後に到達見込み（on_track=True）。
    ``projected_3mo`` は 3 か月後の線形予測（下限 0）。
    """
    import math

    months = _real_months(by_month)
    series = [float(by_month[m]) for m in months]
    current = series[-1] if series else 0.0
    slope = round(_linear_slope(series), 2)
    tgt = float(target)

    if current >= tgt:
        months_to = 0
        on_track = True
    elif slope <= 0:
        months_to = None
        on_track = False
    else:
        months_to = math.ceil((tgt - current) / slope)
        on_track = True

    projected_3mo = round(max(0.0, current + slope * 3), 2)
    return TargetProjection(
        target=tgt,
        current=current,
        slope_per_month=slope,
        on_track=on_track,
        months_to_target=months_to,
        projected_3mo=projected_3mo,
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
