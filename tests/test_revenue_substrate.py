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


def test_hq_outcome_proposes_concrete_monetization_division(tmp_path):
    """リーチ有・収益0・収益化事業部なし → 具体的な ADD_DIVISION（収益化事業部）も提案する。"""
    from core.hierarchy.hq_interventions import HQInterventionProposer

    psm = PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("RevOrg2", "content", status=OrganizationStatus.ACTIVE)
    org.autonomy_score = 75.0
    psm.save_organization(org)
    store = OutcomeStore(platform_home=psm.platform_home)
    store.record("RevOrg2", "impressions", 5000)
    store.record("RevOrg2", "revenue", 0)

    proposals = HQInterventionProposer(psm, source_org_name="HQ").propose_for_org(org)
    add_div = [p for p in proposals if p.target_ref == "add_monetization_division"]
    assert add_div, "収益化事業部が無ければ具体的な ADD_DIVISION 提案が出るはず"
    p = add_div[0]
    assert p.intervention_type == "add_division"
    assert p.intervention_spec["division"]["name"] == "note販売事業部"
    # 変換した spec は executor が読める agents 形式になっている
    assert p.intervention_spec["division"]["teams"][0]["agents"][0]["skills"]


def test_hq_no_add_division_when_monetization_exists(tmp_path):
    """既に収益化事業部があるなら ADD_DIVISION は提案しない（SET_GOAL に委ねる）。"""
    from core.hierarchy.hq_interventions import HQInterventionProposer
    from core.orchestration.division_plugins import add_division_plugin

    psm = PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("RevOrg3", "content", status=OrganizationStatus.ACTIVE)
    org.autonomy_score = 75.0
    add_division_plugin(org, "note_monetization")  # 収益化事業部を既設にする
    psm.save_organization(org)
    store = OutcomeStore(platform_home=psm.platform_home)
    store.record("RevOrg3", "impressions", 5000)
    store.record("RevOrg3", "revenue", 0)

    proposals = HQInterventionProposer(psm, source_org_name="HQ").propose_for_org(org)
    assert not [p for p in proposals if p.target_ref == "add_monetization_division"]
    # 目標設定（why）の方は引き続き出る
    assert [p for p in proposals if p.target_ref == "monetization_from_outcomes"]


# --------------------------------------------------------------------------- #
# レビュー指摘の回帰テスト（堅牢性）                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("bad", ["   ", ".", "sub"])
def test_content_asset_directory_or_blank_path_is_graceful_error(tmp_path, bad):
    """dir/空白を指す file_path は未捕捉例外でなく AssetApplicationError にする。"""
    if bad == "sub":
        (tmp_path / "sub").mkdir()
    prop = build_content_asset_proposal(
        title="x", description="d", file_path=bad, content="X", mode="overwrite"
    )
    with pytest.raises(AssetApplicationError):
        apply_content_asset(prop, repo_root=tmp_path)


def test_outcome_store_tolerates_external_string_value_and_mixed_case(tmp_path):
    """外部ランナーが直接書いた outcomes.json（value 文字列・metric 大文字・不正値）を耐性処理。"""
    import json

    store = OutcomeStore(platform_home=tmp_path)
    (tmp_path / "outcomes.json").write_text(
        json.dumps(
            [
                {"org_name": "Ext", "metric": "Impressions", "value": "5000"},
                {"org_name": "Ext", "metric": "Revenue", "value": "0"},
                {"org_name": "Ext", "metric": "clicks", "value": "bad"},  # 不正→スキップ
            ]
        ),
        encoding="utf-8",
    )
    summary = store.summary_for_org("Ext")
    assert summary.total_reach == 5000.0  # 文字列→数値化 + Impressions→小文字化で reach 計上
    assert summary.total_revenue == 0.0
    assert "clicks" not in summary.by_metric  # 数値化できない event はスキップ（crash しない）


def test_policy_content_asset_by_target_kind_only_requires_human():
    """category が content_asset でなくても target_kind=content_asset なら human_required。"""
    engine = PolicyEngine()
    v = engine.evaluate(
        {
            "category": "style",
            "target_kind": "content_asset",
            "priority": "low",
            "file_path": "articles/b.md",
        }
    )
    assert v.decision == ApprovalDecision.HUMAN_REQUIRED
    assert v.rule_name == "human_required.content_asset"


def test_cli_proposal_apply_content_asset_without_api_key(tmp_path, monkeypatch):
    """content_asset は決定論的なので claude CLI 不要（require_api_key を呼ばない）。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path / "home")
    from types import SimpleNamespace

    from commands.org import cmd_proposal_apply

    workspace = tmp_path / "ws"
    workspace.mkdir()
    psm = PlatformStateManager(platform_home=tmp_path / "home")
    org = create_default_organization("CO", "content", status=OrganizationStatus.ACTIVE)
    org.target_repo_path = str(workspace)
    psm.save_organization(org)
    prop = build_content_asset_proposal(
        title="cli asset", description="d", file_path="a.md", content="hi", mode="create"
    )
    psm.get_org_state_manager(org).save_improvement_proposal(prop)

    def boom(*a, **k):  # require_api_key が呼ばれたら即失敗させる
        raise SystemExit(1)

    asyncio.run(
        cmd_proposal_apply(
            SimpleNamespace(
                org_name="CO",
                proposal_id=str(prop.id)[:8],
                yes=True,
                github_repo=None,
                github_token=None,
            ),
            confirm_action=lambda *a, **k: True,
            get_orchestrator=lambda: None,
            get_psm=lambda: psm,
            require_api_key=boom,
        )
    )
    assert (workspace / "a.md").read_text(encoding="utf-8") == "hi"
