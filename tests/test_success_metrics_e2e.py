"""X.2: Master Plan §12 成功指標を実環境（クリーンな tmp_path）で実際に pass させる E2E 検証。

各テストが §12 の Phase 0 成功指標 1 つに対応し、まっさらなプラットフォーム上で該当フローを
端から端まで駆動して達成を主張する。すべて決定論・LLM 非依存（claude CLI を一切呼ばない）。

GUI 系の §12 指標（組織階層/提案確認の直感的操作）は frontend の vitest スイートが担保するため、
本バックエンド E2E では「データ/ロジック層で §12 が成立する」ことを検証する。
"""

from __future__ import annotations

from core.hierarchy.portfolio_pipeline import scan_portfolio_proposals
from core.metrics.outcomes import OutcomeStore
from core.metrics.revenue_intelligence import analyze_revenue
from core.orchestration.company_plugins import install_company_plugin
from core.org_factory import create_default_organization
from core.platform.state import PlatformStateManager
from core.trends.business_pipeline import scan_business_proposals
from core.trends.models import TrendItem
from core.trends.store import TrendStore


def _platform(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: home)
    return home, PlatformStateManager(platform_home=home)


def test_metric_company_plugin_creates_org_with_agents(tmp_path, monkeypatch):
    """§12: 会社プラグインを追加すると即座に新 Organization が作成され、Agent が動作する。"""
    _home, psm = _platform(tmp_path, monkeypatch)

    result = install_company_plugin("note_sales", psm=psm)
    assert result["agent_count"] >= 1
    assert len(result["divisions"]) >= 1

    org = psm.load_organization_by_name(result["org_name"])
    assert org is not None
    assert len(org.get_all_agents()) >= 1
    # 会社はアプリ内データ（workspace モード）で起動する（§5）。
    assert org.management_mode == "workspace"


def test_metric_manual_revenue_record_and_report(tmp_path, monkeypatch):
    """§12: 手動入力で収益データを記録・集計でき、簡単なレポートが出力できる。"""
    home, _psm = _platform(tmp_path, monkeypatch)
    store = OutcomeStore(platform_home=home)
    store.record("Co", "revenue", 1000, occurred_at="2026-04-10")
    store.record("Co", "revenue", 1500, occurred_at="2026-05-10")
    store.record("Co", "revenue", 2000, occurred_at="2026-06-10")

    by_month = store.revenue_by_month(None)
    assert by_month["2026-04"] == 1000
    assert by_month["2026-06"] == 2000

    report = analyze_revenue(by_month)
    assert report["trend"] == "growing"
    assert report["forecast_next"] > 2000  # 直近成長率で翌月を予測


def test_metric_meta_overseer_proposes_plans_executes(tmp_path, monkeypatch):
    """§12: Meta-Overseer が新しい収益モデル会社を 1 つ提案・計画立案・基本実行できる。"""
    home, psm = _platform(tmp_path, monkeypatch)
    psm.save_organization(create_default_organization("Content Org", "content"))

    # 提案: 高スコアトレンド → 新規会社候補（承認ゲート）
    TrendStore(platform_home=home).add(
        TrendItem(source="web", url="https://x/a", title="新ジャンル爆伸び", score=9.0, genre="ai")
    )
    proposed = scan_business_proposals(platform_home=home, min_score=7.0)
    assert proposed["proposals"] >= 1

    # 計画立案: 月収益目標 → ポートフォリオプラン（承認ゲート）
    OutcomeStore(platform_home=home).record("Content Org", "impressions", 5000)
    planned = scan_portfolio_proposals(target=100000.0, platform_home=home)
    assert planned["proposals"] >= 1

    # 基本実行: 会社プラグイン install → 完全な Organization 起動
    result = install_company_plugin("sns_growth", psm=psm)
    assert psm.load_organization_by_name(result["org_name"]) is not None
    assert result["agent_count"] >= 1


def test_metric_phase0_path_requires_no_claude_cli(tmp_path, monkeypatch):
    """§12 の Phase 0 中核経路は claude CLI 非依存で完結する（クリーン環境で pass）。"""
    home, psm = _platform(tmp_path, monkeypatch)

    def _boom(*_a, **_k):  # pragma: no cover - 呼ばれたら失敗
        raise AssertionError("claude CLI must not be required for Phase 0 success metrics")

    monkeypatch.setattr("core.runtime.claude_code.claude_available", _boom, raising=False)

    result = install_company_plugin("note_sales", psm=psm)
    store = OutcomeStore(platform_home=home)
    store.record(result["org_name"], "revenue", 500, occurred_at="2026-06-01")
    assert store.revenue_by_month(None)["2026-06"] == 500
    assert scan_portfolio_proposals(target=50000.0, platform_home=home)["proposals"] >= 1
