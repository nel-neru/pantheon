"""
Phase 6/7/8 — 収益ドメイン substrate・ワークスペース資産適用・成果フィードバックの検証。

- Phase 6: 収益 skills(enum+YAML) / content_operations テンプレート / content_asset 提案
- Phase 7: ワークスペース内の安全な資産適用（パスガード・冪等）+ approve 経路ディスパッチ
- Phase 8: OutcomeStore + HQ 成果駆動介入（閉じたフライホイール）
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from core.loaders.skill_loader import get_skill_loader
from core.metrics.outcomes import OutcomeStore
from core.models.organization import (
    AgentSkill,
    DivisionType,
    OrganizationStatus,
    is_content_asset_dict,
    is_structural_intervention_dict,
)
from core.orchestration.asset_application import (
    AssetApplicationError,
    apply_content_asset,
    build_content_asset_proposal,
    execute_content_asset,
)
from core.org_factory import create_default_organization, create_organization_from_template
from core.platform.state import PlatformStateManager
from core.policy.engine import ApprovalDecision, PolicyEngine

REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# Phase 6: skills + template                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "skill_id", ["content_strategy", "audience_growth", "performance_marketing"]
)
def test_revenue_skill_enum_and_yaml_align(skill_id):
    assert skill_id in {s.value for s in AgentSkill}
    sd = get_skill_loader().get(skill_id)
    assert sd is not None and sd.id == skill_id


def test_content_operations_template_builds_valid_revenue_org():
    tmpl = REPO_ROOT / "config" / "departments" / "content_operations.yaml"
    org = create_organization_from_template("MyContentOps", "content ops", tmpl, repo_path=None)
    div_types = {d.type for d in org.divisions}
    assert DivisionType.CONTENT_PRODUCTION in div_types
    assert DivisionType.MONETIZATION in div_types
    skills_used = {s.value for a in org.get_all_agents() for s in a.skills}
    assert skills_used & {"content_strategy", "audience_growth", "performance_marketing"}
    # すべての agent が 2〜3 skill 制約を満たす（再バリデーション可能）
    org.model_validate(org.model_dump())


# --------------------------------------------------------------------------- #
# Phase 7: content_asset 安全適用                                              #
# --------------------------------------------------------------------------- #


def test_content_asset_create_overwrite_append(tmp_path):
    prop = build_content_asset_proposal(
        title="article", description="d", file_path="articles/a.md", content="v1", mode="create"
    )
    s = apply_content_asset(prop, repo_root=tmp_path)
    assert s["applied"] is True
    assert (tmp_path / "articles" / "a.md").read_text(encoding="utf-8") == "v1"

    # create 再実行は冪等スキップ
    again = apply_content_asset(prop, repo_root=tmp_path)
    assert again["applied"] is False

    # overwrite
    ow = build_content_asset_proposal(
        title="a2", description="d", file_path="articles/a.md", content="v2", mode="overwrite"
    )
    apply_content_asset(ow, repo_root=tmp_path)
    assert (tmp_path / "articles" / "a.md").read_text(encoding="utf-8") == "v2"

    # append
    ap = build_content_asset_proposal(
        title="a3", description="d", file_path="articles/a.md", content="v3", mode="append"
    )
    apply_content_asset(ap, repo_root=tmp_path)
    assert (tmp_path / "articles" / "a.md").read_text(encoding="utf-8") == "v2v3"


@pytest.mark.parametrize("bad_path", ["../escape.md", "/abs/escape.md", "a/../../escape.md"])
def test_content_asset_path_traversal_blocked(tmp_path, bad_path):
    prop = build_content_asset_proposal(
        title="x", description="d", file_path=bad_path, content="x", mode="create"
    )
    with pytest.raises(AssetApplicationError):
        apply_content_asset(prop, repo_root=tmp_path)


def test_content_asset_missing_workspace_raises(tmp_path):
    prop = build_content_asset_proposal(
        title="x", description="d", file_path="a.md", content="x", mode="create"
    )
    with pytest.raises(AssetApplicationError):
        apply_content_asset(prop, repo_root=tmp_path / "does-not-exist")


def test_content_asset_and_structural_predicates_do_not_overlap():
    asset = build_content_asset_proposal(
        title="x", description="d", file_path="a.md", content="x"
    ).model_dump()
    assert is_content_asset_dict(asset) is True
    assert is_structural_intervention_dict(asset) is False


def test_policy_content_asset_and_external_action_require_human():
    engine = PolicyEngine()
    v1 = engine.evaluate(
        {"category": "content_asset", "file_path": "articles/a.md", "priority": "low"}
    )
    assert v1.decision == ApprovalDecision.HUMAN_REQUIRED
    v2 = engine.evaluate({"category": "external_action", "file_path": "x", "priority": "low"})
    assert v2.decision == ApprovalDecision.HUMAN_REQUIRED


def test_execute_content_asset_via_orchestrator(tmp_path, monkeypatch):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path / "home")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    prop = build_content_asset_proposal(
        title="calendar",
        description="7日分の編集カレンダー",
        file_path="plan/calendar.md",
        content="# Calendar",
    )
    result = asyncio.run(execute_content_asset(prop, repo_path=workspace))
    assert result.success, result.error
    assert (workspace / "plan" / "calendar.md").read_text(encoding="utf-8") == "# Calendar"


def test_web_approve_dispatches_content_asset(tmp_path, monkeypatch):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path / "home")
    import web.server as server

    workspace = tmp_path / "ws"
    workspace.mkdir()
    psm = PlatformStateManager(platform_home=tmp_path / "home")
    org = create_default_organization("ContentOrg", "content", status=OrganizationStatus.ACTIVE)
    org.target_repo_path = str(workspace)
    psm.save_organization(org)
    prop = build_content_asset_proposal(
        title="web article",
        description="d",
        file_path="posts/p1.md",
        content="hello",
        mode="create",
    )
    sm = psm.get_org_state_manager(org)
    sm.save_improvement_proposal(prop)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    from fastapi.testclient import TestClient

    client = TestClient(server.app)
    resp = client.post(f"/api/proposals/{org.name}/{str(prop.id)[:8]}/approve")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "done"
    assert (workspace / "posts" / "p1.md").read_text(encoding="utf-8") == "hello"


# --------------------------------------------------------------------------- #
# Phase 8: outcomes + HQ feedback                                             #
# --------------------------------------------------------------------------- #


def test_outcome_store_record_and_summary(tmp_path):
    store = OutcomeStore(platform_home=tmp_path)
    store.record("Acme", "impressions", 1000, unit="views", source="ga")
    store.record("Acme", "clicks", 50)
    store.record("Acme", "revenue", 0)
    summary = store.summary_for_org("Acme")
    assert summary.event_count == 3
    assert summary.total_reach >= 1000
    assert summary.total_revenue == 0
    assert summary.by_metric["impressions"]["sum"] == 1000


def test_hq_outcome_driven_intervention(tmp_path):
    """リーチはあるが収益 0 の org に、HQ が収益化 SET_GOAL 介入を提案する（閉じたフライホイール）。"""
    from core.hierarchy.hq_interventions import HQInterventionProposer

    psm = PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("RevenueOrg", "content", status=OrganizationStatus.ACTIVE)
    org.autonomy_score = 75.0  # 弱みベースの介入は出ない高スコアにする
    psm.save_organization(org)

    store = OutcomeStore(platform_home=psm.platform_home)
    store.record("RevenueOrg", "impressions", 5000)
    store.record("RevenueOrg", "clicks", 200)
    store.record("RevenueOrg", "revenue", 0)

    proposer = HQInterventionProposer(psm, source_org_name="HQ")
    proposals = proposer.propose_for_org(org)
    goal_props = [p for p in proposals if p.target_ref == "monetization_from_outcomes"]
    assert goal_props, "リーチありで収益0なら収益化目標の介入が出るはず"
    assert goal_props[0].intervention_type == "set_goal"


def test_hq_no_outcome_intervention_when_revenue_present(tmp_path):
    from core.hierarchy.hq_interventions import HQInterventionProposer

    psm = PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("HealthyRev", "content", status=OrganizationStatus.ACTIVE)
    org.autonomy_score = 75.0
    psm.save_organization(org)
    store = OutcomeStore(platform_home=psm.platform_home)
    store.record("HealthyRev", "impressions", 5000)
    store.record("HealthyRev", "revenue", 1200)

    proposer = HQInterventionProposer(psm, source_org_name="HQ")
    proposals = proposer.propose_for_org(org)
    assert not [p for p in proposals if p.target_ref == "monetization_from_outcomes"]
