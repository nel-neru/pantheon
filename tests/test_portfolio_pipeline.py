"""P4.1: 自律経営プランナ（core/hierarchy/portfolio_pipeline）のテスト。

決定論・冪等・LLM 非依存を検証する（claude CLI を一切呼ばない）。
"""

from __future__ import annotations

from core.hierarchy.portfolio_pipeline import (
    build_target_plan,
    compute_revenue_gap,
    preview_portfolio_plan,
    scan_portfolio_proposals,
)
from core.metrics.outcomes import OutcomeStore
from core.org_factory import create_default_organization
from core.platform.state import PlatformStateManager


def _setup(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: home)
    psm = PlatformStateManager(platform_home=home)
    return home, psm


def test_compute_revenue_gap_pure():
    by_month = {"2026-04": 1000.0, "2026-05": 1500.0, "2026-06": 2000.0, "unknown": 999.0}
    gap = compute_revenue_gap(10000.0, by_month)
    assert gap["current"] == 2000.0  # 直近実月（unknown は無視）
    assert gap["target"] == 10000.0
    assert gap["present_gap"] == 8000.0
    assert gap["under_target"] is True
    # forecast は analyze_revenue.forecast_next に一致（直近成長率を適用）
    from core.metrics.revenue_intelligence import analyze_revenue

    assert gap["forecast"] == float(analyze_revenue(by_month)["forecast_next"])
    # 決定論: 同入力で同結果
    assert compute_revenue_gap(10000.0, by_month) == gap


def test_build_target_plan_emphasizes_revenue_when_under_target():
    org_stats = [
        {"org_name": "Reachy", "revenue": 0.0, "reach": 5000.0, "posts": 3.0},
        {"org_name": "Earner", "revenue": 12000.0, "reach": 2000.0, "posts": 5.0},
    ]
    gap = {"under_target": True, "forecast_gap": 5000.0}
    plan = build_target_plan(50000.0, org_stats, gap, min_reach=0.0)
    assert plan  # 何らかの打ち手が出る
    # reach はあるので new_business エスカレーションは出ない（total_reach > 0）
    assert not any(e["kind"] == "new_business" for e in plan)


def test_build_target_plan_escalates_new_business_when_no_reach():
    org_stats = [{"org_name": "Empty", "revenue": 0.0, "reach": 0.0, "posts": 0.0}]
    gap = {"under_target": True, "forecast_gap": 9999.0}
    plan = build_target_plan(99999.0, org_stats, gap, min_reach=0.0)
    assert any(e["kind"] == "new_business" for e in plan)


def test_scan_enqueues_proposed_proposals(tmp_path, monkeypatch):
    home, psm = _setup(tmp_path, monkeypatch)
    psm.save_organization(create_default_organization("Reachy", "集客"))
    store = OutcomeStore(platform_home=home)
    store.record("Reachy", "impressions", 5000)
    store.record("Reachy", "revenue", 0)

    result = scan_portfolio_proposals(target=100000.0, platform_home=home)
    assert result["proposals"] > 0
    proposals = psm.get_org_state_manager(
        psm.load_organization_by_name("Reachy")
    ).get_all_improvement_proposals()
    assert proposals
    assert all(p["status"] == "proposed" for p in proposals)
    assert all(
        p["category"] in {"portfolio_allocation", "cross_org_handoff", "new_business"}
        for p in proposals
    )


def test_scan_is_idempotent_even_when_metrics_change(tmp_path, monkeypatch):
    home, psm = _setup(tmp_path, monkeypatch)
    psm.save_organization(create_default_organization("Reachy", "集客"))
    store = OutcomeStore(platform_home=home)
    store.record("Reachy", "impressions", 5000)

    first = scan_portfolio_proposals(target=100000.0, platform_home=home)
    assert first["proposals"] > 0
    # 実績が変わっても dedupe_key は org_name+action 等で安定 → 二重起票しない
    store.record("Reachy", "revenue", 3000)
    second = scan_portfolio_proposals(target=100000.0, platform_home=home)
    assert second["proposals"] == 0


def test_scan_no_org(tmp_path, monkeypatch):
    home, _psm = _setup(tmp_path, monkeypatch)
    result = scan_portfolio_proposals(target=100000.0, platform_home=home)
    assert result["reason"] == "no_org"


def test_preview_does_not_enqueue(tmp_path, monkeypatch):
    home, psm = _setup(tmp_path, monkeypatch)
    psm.save_organization(create_default_organization("Reachy", "集客"))
    OutcomeStore(platform_home=home).record("Reachy", "impressions", 5000)

    preview = preview_portfolio_plan(target=100000.0, platform_home=home)
    assert "gap" in preview and "plan" in preview
    # 起票されていない
    proposals = psm.get_org_state_manager(
        psm.load_organization_by_name("Reachy")
    ).get_all_improvement_proposals()
    assert proposals == []


def test_scan_does_not_invoke_claude(tmp_path, monkeypatch):
    """LLM 非依存: claude_available を落としても計画・起票が成功する。"""
    home, psm = _setup(tmp_path, monkeypatch)
    psm.save_organization(create_default_organization("Reachy", "集客"))
    OutcomeStore(platform_home=home).record("Reachy", "impressions", 5000)

    def _boom(*a, **k):  # pragma: no cover - 呼ばれたら失敗させる
        raise AssertionError("claude CLI must not be invoked on the deterministic path")

    monkeypatch.setattr("core.runtime.claude_code.claude_available", _boom, raising=False)
    result = scan_portfolio_proposals(target=100000.0, platform_home=home)
    assert result["proposals"] > 0
