"""
Phase 5 — HQ 構造的介入（cross-org structural intervention）の検証。

カバー範囲:
- モデル拡張（ImprovementProposal の介入フィールド round-trip / is_structural_intervention）
- PolicyEngine: 構造介入は必ず HUMAN_REQUIRED（auto_reject も auto_approve もしない）
- 純粋ミューテーション apply_intervention_to_org（add_division/team/agent/inject_skills、冪等、スキル制約）
- apply_structural_intervention（ロード→変更→永続化、system org 拒否、set_goal）
- execute_structural_intervention（PreTaskOrchestrator 経由のエンドツーエンド）
- HQInterventionProposer（診断→提案生成→子 org へ保存→dedupe）
- 既存 approve 経路（Web）への構造介入ディスパッチ
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from core.models.organization import (
    STRUCTURAL_INTERVENTION_CATEGORY,
    ImprovementProposal,
    OrganizationStatus,
    StructuralInterventionType,
)
from core.orchestration.structural_intervention import (
    StructuralInterventionError,
    apply_intervention_to_org,
    apply_structural_intervention,
    build_intervention_proposal,
    execute_structural_intervention,
)
from core.org_factory import create_default_organization
from core.platform.state import PlatformStateManager
from core.policy.engine import ApprovalDecision, PolicyEngine

# --------------------------------------------------------------------------- #
# モデル                                                                       #
# --------------------------------------------------------------------------- #


def test_proposal_intervention_fields_round_trip():
    proposal = ImprovementProposal(
        review_id=uuid4(),
        title="add division",
        description="d",
        category=STRUCTURAL_INTERVENTION_CATEGORY,
        is_meta=True,
        target_org_id="abc",
        target_org_name="Child",
        source_org_name="HQ",
        intervention_type="add_division",
        target_kind="org_structure",
        target_ref="QA",
        intervention_spec={"division": {"name": "QA"}},
    )
    assert proposal.is_structural_intervention()
    reloaded = ImprovementProposal.model_validate_json(proposal.model_dump_json())
    assert reloaded.target_org_name == "Child"
    assert reloaded.intervention_spec == {"division": {"name": "QA"}}
    assert reloaded.is_structural_intervention()


def test_existing_proposal_json_without_new_fields_still_loads():
    """新フィールドは Optional + デフォルトなので、旧 JSON も読み戻せる（後方互換）。"""
    legacy = '{"review_id":"%s","title":"t","description":"d"}' % uuid4()
    proposal = ImprovementProposal.model_validate_json(legacy)
    assert proposal.target_org_id is None
    assert proposal.is_structural_intervention() is False


# --------------------------------------------------------------------------- #
# PolicyEngine                                                                 #
# --------------------------------------------------------------------------- #


def test_policy_structural_intervention_is_human_required():
    engine = PolicyEngine()
    verdict = engine.evaluate(
        {
            "category": "structural_intervention",
            "is_meta": True,
            "file_path": "",
            "priority": "high",
            "intervention_type": "add_division",
            "target_org_name": "Child",
        }
    )
    assert verdict.decision == ApprovalDecision.HUMAN_REQUIRED
    assert verdict.rule_name == "intervention.cross_org"


def test_policy_intervention_not_auto_rejected_without_is_meta():
    """is_meta が無くても target_org が立っていれば auto_reject せず human_required にする。"""
    engine = PolicyEngine()
    verdict = engine.evaluate(
        {
            "category": "structural_intervention",
            "file_path": "",
            "priority": "low",
            "target_org_id": "xyz",
            "intervention_type": "add_team",
        }
    )
    assert verdict.decision == ApprovalDecision.HUMAN_REQUIRED


def test_policy_normal_meta_empty_file_still_human_required():
    """通常の meta 提案（介入でない）は従来どおり human_required（auto_reject されない）。"""
    engine = PolicyEngine()
    verdict = engine.evaluate({"is_meta": True, "category": "meta", "file_path": ""})
    assert verdict.decision == ApprovalDecision.HUMAN_REQUIRED
    # 介入ルールではなくカテゴリ/デフォルト経由であることを確認
    assert verdict.rule_name != "intervention.cross_org"


# --------------------------------------------------------------------------- #
# 純粋ミューテーション                                                          #
# --------------------------------------------------------------------------- #


def test_apply_add_division_is_idempotent():
    org = create_default_organization("Child", "test")
    spec = {
        "division": {
            "name": "品質保証部",
            "type": "quality_assurance",
            "teams": [
                {
                    "name": "QA Team",
                    "agents": [
                        {"name": "QA", "skills": ["performance_analysis", "tool_integration"]}
                    ],
                }
            ],
        }
    }
    before = len(org.divisions)
    summary = apply_intervention_to_org(
        org, intervention_type="add_division", intervention_spec=spec
    )
    assert summary["applied"] is True
    assert len(org.divisions) == before + 1
    # 再適用は冪等（追加しない）
    again = apply_intervention_to_org(org, intervention_type="add_division", intervention_spec=spec)
    assert again["applied"] is False


def test_apply_add_division_defaults_team_and_agent_with_valid_skills():
    org = create_default_organization("Child", "test")
    spec = {"division": {"name": "新部門", "type": "org_evolution"}}
    apply_intervention_to_org(org, intervention_type="add_division", intervention_spec=spec)
    # デフォルトの team + agent が作られ、スキルは 2〜3 個に正規化される
    new_div = next(d for d in org.divisions if d.name == "新部門")
    agent = new_div.teams[0].agents[0]
    assert 2 <= len(agent.skills) <= 3
    # モデル全体が再バリデーション可能（skills 制約を満たす）
    org.model_validate(org.model_dump())


def test_apply_add_team_and_agent():
    org = create_default_organization("Child", "test")
    division_name = org.divisions[0].name
    team_summary = apply_intervention_to_org(
        org,
        intervention_type="add_team",
        intervention_spec={"division": division_name, "team": {"name": "新チーム"}},
    )
    assert team_summary["applied"] is True
    agent_summary = apply_intervention_to_org(
        org,
        intervention_type="add_agent",
        intervention_spec={
            "division": division_name,
            "team": "新チーム",
            "agent": {"name": "新人", "skills": ["org_design", "strategic_planning"]},
        },
    )
    assert agent_summary["applied"] is True
    names = [a.name for a in org.get_all_agents()]
    assert "新人" in names


def test_apply_add_team_missing_division_raises():
    org = create_default_organization("Child", "test")
    with pytest.raises(StructuralInterventionError):
        apply_intervention_to_org(
            org,
            intervention_type="add_team",
            intervention_spec={"division": "存在しない部門", "team": {"name": "x"}},
        )


def test_apply_inject_skills_respects_cap():
    org = create_default_organization("Child", "test")
    agent = org.get_all_agents()[0]
    agent_name = agent.name
    # 既存 2 スキル + 2 個注入 → cap(3) で 1 個だけ入り 1 個 skip
    summary = apply_intervention_to_org(
        org,
        intervention_type="inject_skills",
        intervention_spec={"agent": agent_name, "skills": ["org_design", "prompt_engineering"]},
    )
    assert len(agent.skills) == 3
    assert summary["skills_skipped_at_cap"]  # 余りは cap で skip
    org.model_validate(org.model_dump())


def test_apply_unknown_intervention_type_raises():
    org = create_default_organization("Child", "test")
    with pytest.raises(StructuralInterventionError):
        apply_intervention_to_org(org, intervention_type="nonsense", intervention_spec={})


# --------------------------------------------------------------------------- #
# I/O ラッパ + 永続化                                                          #
# --------------------------------------------------------------------------- #


def _setup_psm_with_child(tmp_path):
    psm = PlatformStateManager(platform_home=tmp_path)
    child = create_default_organization("Child", "child org", status=OrganizationStatus.ACTIVE)
    psm.save_organization(child)
    return psm, child


def test_apply_structural_intervention_persists(tmp_path):
    psm, child = _setup_psm_with_child(tmp_path)
    proposal = build_intervention_proposal(
        target_org=child,
        intervention_type=StructuralInterventionType.ADD_DIVISION.value,
        title="add QA",
        description="d",
        intervention_spec={"division": {"name": "品質保証部", "type": "quality_assurance"}},
        source_org_name="HQ",
        target_ref="品質保証部",
    )
    summary = apply_structural_intervention(proposal, psm=psm)
    assert summary["applied"] is True
    # グローバルストアから読み直して反映を確認
    reloaded = psm.load_organization_by_id(str(child.id))
    assert any(d.name == "品質保証部" for d in reloaded.divisions)


def test_apply_structural_intervention_refuses_system_org(tmp_path):
    psm = PlatformStateManager(platform_home=tmp_path)
    system_org = create_default_organization("HQ", "meta", is_system=True)
    psm.save_organization(system_org)
    proposal = build_intervention_proposal(
        target_org=system_org,
        intervention_type=StructuralInterventionType.ADD_DIVISION.value,
        title="x",
        description="d",
        intervention_spec={"division": {"name": "y"}},
    )
    with pytest.raises(StructuralInterventionError):
        apply_structural_intervention(proposal, psm=psm)


def test_apply_structural_intervention_set_goal(tmp_path):
    psm, child = _setup_psm_with_child(tmp_path)
    proposal = build_intervention_proposal(
        target_org=child,
        intervention_type=StructuralInterventionType.SET_GOAL.value,
        title="set goal",
        description="d",
        intervention_spec={"goal": "提案品質を高める", "target_category": "maintainability"},
        source_org_name="HQ",
    )
    summary = apply_structural_intervention(proposal, psm=psm)
    assert summary["applied"] is True
    from core.hierarchy.org_goals import OrgGoalManager

    goals = OrgGoalManager(platform_home=psm.platform_home).get_active_goals("Child")
    assert any(g.description == "提案品質を高める" for g in goals)


def test_apply_structural_intervention_missing_target_raises(tmp_path):
    psm = PlatformStateManager(platform_home=tmp_path)
    proposal = {
        "title": "x",
        "intervention_type": "add_division",
        "target_org_name": "DoesNotExist",
        "intervention_spec": {"division": {"name": "z"}},
    }
    with pytest.raises(StructuralInterventionError):
        apply_structural_intervention(proposal, psm=psm)


# --------------------------------------------------------------------------- #
# エンドツーエンド（PreTaskOrchestrator 経由）                                  #
# --------------------------------------------------------------------------- #


def test_execute_structural_intervention_via_orchestrator(tmp_path, monkeypatch):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    psm, child = _setup_psm_with_child(tmp_path)
    proposal = build_intervention_proposal(
        target_org=child,
        intervention_type=StructuralInterventionType.ADD_DIVISION.value,
        title="add content production",
        description="HQ が ContentProduction Division を追加",
        intervention_spec={
            "division": {
                "name": "ContentProduction",
                "type": "org_evolution",
                "teams": [
                    {
                        "name": "Writers",
                        "agents": [
                            {"name": "Writer", "skills": ["deep_research", "knowledge_curation"]}
                        ],
                    }
                ],
            }
        },
        source_org_name="HQ",
        target_ref="ContentProduction",
    )
    result = asyncio.run(execute_structural_intervention(proposal, psm=psm))
    assert result.success, result.error
    reloaded = psm.load_organization_by_id(str(child.id))
    assert any(d.name == "ContentProduction" for d in reloaded.divisions)


# --------------------------------------------------------------------------- #
# HQ プロポーザ                                                                #
# --------------------------------------------------------------------------- #


def test_hq_proposer_generates_and_persists_for_weak_org(tmp_path):
    from core.hierarchy.hq_interventions import HQInterventionProposer

    psm = PlatformStateManager(platform_home=tmp_path)
    weak = create_default_organization("WeakOrg", "weak", status=OrganizationStatus.ACTIVE)
    weak.autonomy_score = 20.0  # health < 50 → 弱み「自律スコアの改善が必要」
    psm.save_organization(weak)
    # system org は対象外
    system_org = create_default_organization("HQ", "meta", is_system=True)
    psm.save_organization(system_org)

    proposer = HQInterventionProposer(psm, source_org_name="HQ")
    targets = proposer.list_target_orgs()
    assert [o.name for o in targets] == ["WeakOrg"]

    created = proposer.propose_all(persist=True)
    assert created, "弱みから少なくとも 1 件の介入提案が出るはず"
    assert all(p.category == STRUCTURAL_INTERVENTION_CATEGORY for p in created)
    assert all(p.target_org_name == "WeakOrg" for p in created)

    # 子 org のストアに保存され、再実行では dedupe されて 0 件
    sm = psm.get_org_state_manager(weak)
    pending = sm.get_pending_improvement_proposals(limit=50)
    assert any(p.get("category") == STRUCTURAL_INTERVENTION_CATEGORY for p in pending)
    second = proposer.propose_all(persist=True)
    assert second == []


def test_hq_proposer_then_apply_end_to_end(tmp_path, monkeypatch):
    """HQ が提案 → 保存 → execute_structural_intervention で適用、までの一連。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    from core.hierarchy.hq_interventions import HQInterventionProposer

    psm = PlatformStateManager(platform_home=tmp_path)
    weak = create_default_organization("WeakOrg", "weak", status=OrganizationStatus.ACTIVE)
    weak.autonomy_score = 10.0
    psm.save_organization(weak)

    proposer = HQInterventionProposer(psm, source_org_name="HQ")
    created = proposer.propose_all(persist=True)
    add_division = next(
        (
            p
            for p in created
            if p.intervention_type == StructuralInterventionType.ADD_DIVISION.value
        ),
        None,
    )
    assert add_division is not None
    result = asyncio.run(execute_structural_intervention(add_division, psm=psm))
    assert result.success, result.error
    reloaded = psm.load_organization_by_id(str(weak.id))
    assert len(reloaded.divisions) >= 2  # 元の Core + HQ 介入で追加された Division


# --------------------------------------------------------------------------- #
# Web approve 経路への統合                                                      #
# --------------------------------------------------------------------------- #


def test_web_approve_dispatches_structural_intervention(tmp_path, monkeypatch):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    import web.server as server

    psm = PlatformStateManager(platform_home=tmp_path)
    child = create_default_organization("Child", "child", status=OrganizationStatus.ACTIVE)
    psm.save_organization(child)
    proposal = build_intervention_proposal(
        target_org=child,
        intervention_type=StructuralInterventionType.ADD_DIVISION.value,
        title="web add division",
        description="d",
        intervention_spec={"division": {"name": "WebAdded", "type": "org_evolution"}},
        source_org_name="HQ",
        target_ref="WebAdded",
    )
    sm = psm.get_org_state_manager(child)
    sm.save_improvement_proposal(proposal)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    from fastapi.testclient import TestClient

    client = TestClient(server.app)
    response = client.post(f"/api/proposals/{child.name}/{str(proposal.id)[:8]}/approve")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "done"
    assert body["policy"]["decision"] == "human_required"
    reloaded = psm.load_organization_by_id(str(child.id))
    assert any(d.name == "WebAdded" for d in reloaded.divisions)


# --------------------------------------------------------------------------- #
# CLI（pantheon hq propose / apply）                                            #
# --------------------------------------------------------------------------- #


def test_cli_hq_propose_then_apply(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    from types import SimpleNamespace

    from commands.hq import cmd_hq_apply, cmd_hq_propose

    psm = PlatformStateManager(platform_home=tmp_path)
    weak = create_default_organization("WeakOrg", "weak", status=OrganizationStatus.ACTIVE)
    weak.autonomy_score = 10.0
    psm.save_organization(weak)

    # propose（保存）
    asyncio.run(cmd_hq_propose(SimpleNamespace(dry_run=False), get_psm=lambda: psm))
    out = capsys.readouterr().out
    assert "構造介入提案" in out

    # 保存された add_division 提案を取得
    sm = psm.get_org_state_manager(weak)
    pending = sm.get_pending_improvement_proposals(limit=50)
    add_division = next(
        p
        for p in pending
        if p.get("intervention_type") == StructuralInterventionType.ADD_DIVISION.value
    )

    # apply（Policy + PreTask 経由）
    asyncio.run(
        cmd_hq_apply(
            SimpleNamespace(proposal_id=str(add_division["id"])[:8], org_name="WeakOrg", yes=True),
            confirm_action=lambda *a, **k: True,
            get_psm=lambda: psm,
            require_api_key=lambda *a, **k: None,
        )
    )
    reloaded = psm.load_organization_by_id(str(weak.id))
    assert len(reloaded.divisions) >= 2
    # ステータスは done に
    done = psm.get_org_state_manager(reloaded).get_pending_improvement_proposals(limit=50)
    assert not any(str(p.get("id")) == str(add_division["id"]) for p in done)


def test_cli_hq_apply_rejects_non_intervention(tmp_path, monkeypatch):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    from types import SimpleNamespace

    from commands.hq import cmd_hq_apply

    psm = PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("Child", "child", status=OrganizationStatus.ACTIVE)
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)
    normal = ImprovementProposal(
        review_id=uuid4(), title="normal", description="d", file_path="a.py", category="style"
    )
    sm.save_improvement_proposal(normal)

    with pytest.raises(SystemExit):
        asyncio.run(
            cmd_hq_apply(
                SimpleNamespace(proposal_id=str(normal.id)[:8], org_name="Child", yes=True),
                confirm_action=lambda *a, **k: True,
                get_psm=lambda: psm,
                require_api_key=lambda *a, **k: None,
            )
        )
