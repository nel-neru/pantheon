"""core.metrics.revenue_intelligence の単体テスト（決定論・LLM なし）。"""

from __future__ import annotations

from core.metrics.revenue_intelligence import analyze_revenue


def test_growing_trend_and_forecast():
    a = analyze_revenue({"2026-01": 100, "2026-02": 150, "2026-03": 225})
    assert a["months"] == ["2026-01", "2026-02", "2026-03"]
    assert a["trend"] == "growing"
    assert a["latest_change_pct"] == 50.0
    assert a["forecast_next"] > 225  # 上昇トレンドを外挿


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
