"""C-4: capability gap → agent spawn / Team・Division 構造提案のテスト。"""

from __future__ import annotations

from core.intelligence.capability_gap_analyzer import CapabilityGap
from core.models.organization import Organization
from core.orchestration.capability_gap_loop import (
    CapabilityGapResolver,
    resolve_gaps_for_org,
)


def _gap(stype, name, **kw):
    return CapabilityGap(
        gap_id=kw.get("gap_id", f"gap:{name}"),
        pattern_key=kw.get("pattern_key", "p"),
        description=kw.get("description", "desc"),
        suggested_type=stype,
        suggested_name=name,
        rationale=kw.get("rationale", "needed"),
        priority=kw.get("priority", "medium"),
    )


def test_agent_gap_spawns_agent():
    org = Organization(name="X", purpose="p")
    resolver = CapabilityGapResolver()
    results = resolver.resolve([_gap("agent", "deep_research")], org)
    assert len(results) == 1
    assert results[0].action == "spawned_agent"
    assert results[0].auto_applied is True


def test_skill_gap_spawns_agent():
    org = Organization(name="X", purpose="p")
    results = CapabilityGapResolver().resolve([_gap("skill", "codebase_exploration")], org)
    assert results[0].action == "spawned_agent"


def test_team_gap_standard_org_is_human_required_by_default():
    # 既定ポリシーでは構造変更は人間承認ゲートを通る（無条件 auto 適用しない＝HITL 整合）
    org = Organization(name="X", purpose="p", isolation_level="standard")
    before = len(org.divisions)
    results = CapabilityGapResolver().resolve([_gap("team", "GameEngineTeam")], org)
    assert results[0].action == "proposed_team"
    assert results[0].auto_applied is False
    assert len(org.divisions) == before  # 既定では自動適用しない


def test_division_gap_external_org_gated_by_boundary_rule():
    # external org の構造提案は境界ガード（org_boundary.out_of_scope）で人間確認に倒れる。
    # cross-org 介入ルールではなく、本物の境界ガードが発火することを検証する。
    org = Organization(
        name="Ext", purpose="p", isolation_level="external", allowed_path_scope=["content/"]
    )
    before = len(org.divisions)
    results = CapabilityGapResolver().resolve([_gap("division", "VideoEditDivision")], org)
    assert results[0].action == "proposed_division"
    assert results[0].auto_applied is False
    assert "org_boundary.out_of_scope" in results[0].detail  # 本物の境界ガード
    assert len(org.divisions) == before


def test_team_gap_auto_applies_when_policy_allows():
    # policy が org_structure を AUTO_APPROVE する運用にした場合は実際に Team が適用される
    # （_apply_structure の適用パスと skills 2-3 制約を検証）
    from core.policy.engine import ApprovalDecision, PolicyVerdict

    class _AutoPolicy:
        def evaluate(self, proposal, *, org_context=None):
            return PolicyVerdict(
                decision=ApprovalDecision.AUTO_APPROVE, reason="test", rule_name="test.auto"
            )

    org = Organization(name="X", purpose="p", isolation_level="standard")
    before = len(org.divisions)
    resolver = CapabilityGapResolver(policy=_AutoPolicy())
    results = resolver.resolve([_gap("division", "GameEngineDiv")], org)
    assert results[0].auto_applied is True
    assert len(org.divisions) == before + 1
    agents = org.get_all_agents()
    assert agents and all(2 <= len(a.skills) <= 3 for a in agents)


def test_auto_applied_structure_proposal_excluded_from_inbox_pending(tmp_path, monkeypatch):
    # auto-apply（policy が org_structure を AUTO_APPROVE）で構造変更が即適用された場合、
    # 永続化される提案は status="done"（非アクティブ）になり、/inbox の承認経路
    # （get_pending_improvement_proposals = web の _pending_proposals_for が使う）に
    # 出てこない＝既に適用済みの構造変更を人間が二重承認できない、を固定する。
    # （human-required 経路の status="pending" は active で出る、の対称）。
    from core.org_factory import create_default_organization
    from core.platform.state import PlatformStateManager
    from core.policy.engine import ApprovalDecision, PolicyVerdict

    class _AutoPolicy:
        def evaluate(self, proposal, *, org_context=None):
            return PolicyVerdict(
                decision=ApprovalDecision.AUTO_APPROVE, reason="test", rule_name="test.auto"
            )

    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    psm = PlatformStateManager(platform_home=tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    org = create_default_organization("Org", "p", repo_path=str(repo))
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)
    before = len(org.divisions)

    resolver = CapabilityGapResolver(policy=_AutoPolicy(), state_manager=sm)
    results = resolver.resolve([_gap("division", "GameEngineDiv")], org)

    # 構造は実際に in-memory 適用される
    assert results[0].auto_applied is True
    assert len(org.divisions) == before + 1

    # 監査証跡として永続化はされるが status="done"（非アクティブ）
    all_props = sm.get_all_improvement_proposals()
    structure = [p for p in all_props if p.get("category") == "org_structure"]
    assert structure, "auto-applied 構造提案は監査証跡として永続化されるべき"
    assert structure[0]["status"] == "done"

    # /inbox の pending 経路には出ない（既適用を人間が再承認できない）。
    # status 文字列ではなく永続化された提案の id を直接照合し、pending フィルタが
    # 壊れた場合（status 判定とは独立に）にも回帰を捕まえる。
    applied_id = structure[0]["id"]
    pending = sm.get_pending_improvement_proposals()
    pending_ids = {p.get("id") for p in pending}
    assert applied_id not in pending_ids, (
        "auto-applied 済みの構造提案が /inbox の承認待ちに出てはならない（二重承認防止）"
    )
    assert not any(p.get("category") == "org_structure" for p in pending)


def test_already_implemented_gap_skipped():
    org = Organization(name="X", purpose="p")
    gap = _gap("agent", "deep_research")
    gap.implemented = True
    results = CapabilityGapResolver().resolve([gap], org)
    assert results[0].action == "skipped"


def test_resolve_gaps_for_org_summary():
    org = Organization(name="X", purpose="p", isolation_level="standard")
    gaps = [
        _gap("agent", "deep_research"),
        _gap("team", "GrowthTeam"),
        _gap("division", "MonetizationDiv"),
    ]
    summary = resolve_gaps_for_org(gaps, org)
    assert summary["total"] == 3
    assert summary["spawned_agents"] == 1
    assert summary["proposed_teams"] == 1
    assert summary["proposed_divisions"] == 1


def test_structure_proposal_persisted_when_sm_given(tmp_path, monkeypatch):
    from core.org_factory import create_default_organization
    from core.platform.state import PlatformStateManager

    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    psm = PlatformStateManager(platform_home=tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    org = create_default_organization("Org", "p", repo_path=str(repo))
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)

    resolver = CapabilityGapResolver(state_manager=sm)
    resolver.resolve([_gap("team", "NewTeam")], org)
    proposals = sm.get_all_improvement_proposals()
    assert any(p["category"] == "org_structure" for p in proposals)
