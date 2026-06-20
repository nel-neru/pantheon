"""core.metrics.revenue_intelligence の単体テスト（決定論・LLM なし）。"""

from __future__ import annotations

from core.metrics.revenue_intelligence import analyze_revenue


def test_growing_trend_and_forecast():
    a = analyze_revenue({"2026-01": 100, "2026-02": 150, "2026-03": 225})
    assert a["months"] == ["2026-01", "2026-02", "2026-03"]
    assert a["trend"] == "growing"
    assert a["latest_change_pct"] == 50.0
    assert a["forecast_next"] > 225  # 上昇トレンドを外挿


def test_mom_change_is_adjacent_pairs_n_minus_1():
    # 隣接ペア（前月,当月）の MoM は N 要素から N-1 個出る＝series と series[1:] の
    # 意図的な長さ差（zip の strict=False 切り捨て）の不変条件を固定する。
    # ここを strict=True に「誤修正」すると ValueError で落ちて回帰が検出される。
    a = analyze_revenue({"2026-01": 100, "2026-02": 150, "2026-03": 225})
    assert a["mom_change_pct"] == [50.0, 50.0]  # 3 ヶ月 → 2 個（N-1）


def test_declining_trend():
    a = analyze_revenue({"2026-01": 300, "2026-02": 200, "2026-03": 150})
    assert a["trend"] == "declining"
    assert a["latest_change_pct"] == -25.0


def test_flat_trend_within_threshold():
    a = analyze_revenue({"2026-01": 100, "2026-02": 102, "2026-03": 101})
    assert a["trend"] == "flat"


def test_insufficient_data():
    a = analyze_revenue({"2026-06": 1000})
    assert a["trend"] == "insufficient"
    assert a["forecast_next"] == 1000.0
    assert a["latest_change_pct"] is None


def test_zero_previous_month_is_safe():
    a = analyze_revenue({"2026-01": 0, "2026-02": 100})
    # 前月 0 は割れないので MoM は None、トレンドは flat、予測は据え置き
    assert a["mom_change_pct"] == [None]
    assert a["latest_change_pct"] is None
    assert a["trend"] == "flat"
    assert a["forecast_next"] == 100.0


def test_unknown_bucket_excluded():
    a = analyze_revenue({"unknown": 999, "2026-01": 100, "2026-02": 120})
    assert a["months"] == ["2026-01", "2026-02"]
    assert a["trend"] == "growing"


def test_forecast_confidence_band_brackets_point_estimate():
    """予測バンドは点推定を挟み、下限は 0 未満にならない（finding 15）。"""
    a = analyze_revenue({"2026-01": 100, "2026-02": 150, "2026-03": 225})
    assert a["forecast_lower"] <= a["forecast_next"] <= a["forecast_upper"]
    assert a["forecast_lower"] >= 0.0


def test_forecast_band_widens_with_volatility():
    """成長率のばらつきが大きいほどバンドは広い（一定成長はスプレッド 0）。"""
    steady = analyze_revenue({"2026-01": 100, "2026-02": 110, "2026-03": 121})  # +10% 一定
    volatile = analyze_revenue({"2026-01": 100, "2026-02": 200, "2026-03": 210})  # +100%,+5%
    steady_width = steady["forecast_upper"] - steady["forecast_lower"]
    volatile_width = volatile["forecast_upper"] - volatile["forecast_lower"]
    assert steady_width == 0.0  # 一定成長 → ばらつき無し
    assert volatile_width > steady_width


def test_insufficient_data_band_is_point():
    a = analyze_revenue({"2026-06": 1000})
    assert a["forecast_lower"] == a["forecast_next"] == a["forecast_upper"] == 1000.0


def test_analyze_revenue_extended_perfect_linear():
    """完全線形系列は R²=1.0、傾きを正しく外挿する（多か月 OLS 予測）。"""
    from core.metrics.revenue_intelligence import analyze_revenue_extended

    a = analyze_revenue_extended({"2026-01": 100, "2026-02": 200, "2026-03": 300}, horizon=3)
    assert a["slope_per_month"] == 100.0
    assert a["r_squared"] == 1.0
    assert a["trend"] == "growing"
    assert a["forecast"] == [400.0, 500.0, 600.0]


def test_analyze_revenue_extended_floors_at_zero_and_insufficient():
    from core.metrics.revenue_intelligence import analyze_revenue_extended

    # 急減トレンドでも予測は 0 未満にならない
    a = analyze_revenue_extended({"2026-01": 300, "2026-02": 100}, horizon=5)
    assert all(v >= 0.0 for v in a["forecast"])
    # 1 点は insufficient
    b = analyze_revenue_extended({"2026-01": 500}, horizon=3)
    assert b["trend"] == "insufficient"


def test_project_to_target_reachable_growing():
    """上昇トレンドなら目標到達までの月数を回帰 run-rate で射影する（新能力）。"""
    from core.metrics.revenue_intelligence import project_to_target

    # +100/月の一定トレンド、直近 300、目標 600 → あと 3 か月。
    p = project_to_target({"2026-01": 100, "2026-02": 200, "2026-03": 300}, 600)
    assert p["current"] == 300
    assert p["slope_per_month"] == 100.0
    assert p["on_track"] is True
    assert p["months_to_target"] == 3
    assert p["projected_3mo"] == 600.0


def test_project_to_target_already_met():
    from core.metrics.revenue_intelligence import project_to_target

    p = project_to_target({"2026-01": 500, "2026-02": 1200}, 1000)
    assert p["months_to_target"] == 0 and p["on_track"] is True


def test_project_to_target_declining_is_unreachable():
    from core.metrics.revenue_intelligence import project_to_target

    p = project_to_target({"2026-01": 500, "2026-02": 400, "2026-03": 300}, 1000)
    assert p["on_track"] is False and p["months_to_target"] is None
    assert p["slope_per_month"] < 0


def test_revenue_by_month_date_range_filter(tmp_path):
    """revenue_by_month が start_date/end_date で期間を絞る（finding 24）。"""
    from core.metrics.outcomes import OutcomeStore

    store = OutcomeStore(platform_home=tmp_path)
    store.record("Co", "revenue", 100, occurred_at="2026-01-10")
    store.record("Co", "revenue", 200, occurred_at="2026-02-10")
    store.record("Co", "revenue", 400, occurred_at="2026-03-10")

    full = store.revenue_by_month("Co")
    assert full == {"2026-01": 100, "2026-02": 200, "2026-03": 400}
    # 2 月以降のみ
    feb_on = store.revenue_by_month("Co", start_date="2026-02-01")
    assert feb_on == {"2026-02": 200, "2026-03": 400}
    # 1〜2 月のみ
    jan_feb = store.revenue_by_month("Co", start_date="2026-01-01", end_date="2026-02-28")
    assert jan_feb == {"2026-01": 100, "2026-02": 200}


def test_revenue_impact_rank_high_medium_none():
    from core.metrics.revenue_intelligence import revenue_impact_rank

    # 収益化に直結 = 2
    assert revenue_impact_rank({"target_ref": "add_monetization_division"}) == 2
    assert revenue_impact_rank({"target_ref": "monetization_from_outcomes"}) == 2
    assert revenue_impact_rank({"intervention_spec": {"division": {"type": "monetization"}}}) == 2
    assert revenue_impact_rank({"intervention_spec": {"target_category": "performance"}}) == 2
    # 集客/コンテンツ = 1
    assert (
        revenue_impact_rank({"intervention_spec": {"division": {"type": "audience_development"}}})
        == 1
    )
    assert revenue_impact_rank({"category": "content_asset"}) == 1
    # それ以外・欠損 = 0
    assert revenue_impact_rank({"target_ref": "実行強化部"}) == 0
    assert revenue_impact_rank({}) == 0
    assert revenue_impact_rank(None) == 0  # type: ignore[arg-type]
