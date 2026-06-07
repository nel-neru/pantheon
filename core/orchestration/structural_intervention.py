"""
Structural Intervention — HQ（Meta-Improvement Organization）が別 Organization の
構造を安全に変更するための中核ロジック（Phase 5）。

設計思想:
- 既存の analyze → ImprovementProposal → PolicyEngine → 適用 + 学習 ループを
  「ファイル変更」から「組織モデル変更」へ *一般化* する（並行システムを作らない）。
- 変更は Organization / Division / Team / SpecialistAgent モデル内に閉じる（任意の
  ファイル書き込みや外部アクションは行わない）= 最も安全な介入面。
- 適用は **PolicyEngine 承認後** にのみ呼ばれる前提（このモジュール自身はポリシーを
  通さない。呼び出し側＝承認経路の責務）。

提供物:
- ``StructuralInterventionError`` — 介入が適用できないときの明示エラー。
- ``build_intervention_proposal`` — 安定した dedupe_key / review_id 付きで
  構造介入 ``ImprovementProposal`` を組み立てる（HQ プロポーザが使う）。
- ``apply_intervention_to_org`` — 純粋な（I/O なし）組織モデル変更。冪等。
- ``apply_structural_intervention`` — 提案を受けて対象 org をロード→変更→永続化する
  I/O ラッパ（executor agent / CLI / Web から呼ばれる）。
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import UUID, uuid5

from core.models.organization import (
    STRUCTURAL_INTERVENTION_CATEGORY,
    STRUCTURAL_INTERVENTION_TYPES,
    AgentSkill,
    Division,
    DivisionType,
    ImprovementProposal,
    Organization,
    SpecialistAgent,
    StructuralInterventionType,
    Team,
)

if TYPE_CHECKING:
    from core.platform.state import PlatformStateManager

# build_intervention_proposal の review_id を安定生成するための名前空間。
_REVIEW_NAMESPACE = UUID("a7f1c0de-5e10-4b2a-9c33-0f5e5e5e5e5e")


class StructuralInterventionError(ValueError):
    """構造介入を適用できないときに送出する（呼び出し側で 4xx/失敗に変換）。"""


# ---------------------------------------------------------------------------
# スキル / DivisionType の安全な解決（2〜3 スキル制約を必ず満たす）
# ---------------------------------------------------------------------------


def _resolve_division_type(raw_value: str | None) -> DivisionType:
    normalized = (raw_value or "").strip().lower()
    for division_type in DivisionType:
        if normalized in {division_type.value.lower(), division_type.name.lower()}:
            return division_type
    return DivisionType.ORG_EVOLUTION


def _resolve_skills(raw_skills: List[str] | None) -> List[AgentSkill]:
    """文字列スキル列を 2〜3 個の有効な AgentSkill に正規化する。

    SpecialistAgent.skills は Field(min_length=2, max_length=3) のため、ここで必ず
    2〜3 個に収める（不正名は無視し、不足は STRATEGIC_PLANNING / DEEP_RESEARCH で補完）。
    """
    resolved: List[AgentSkill] = []
    for raw_skill in raw_skills or []:
        normalized = (str(raw_skill) or "").strip().lower()
        match = next(
            (s for s in AgentSkill if normalized in {s.value.lower(), s.name.lower()}),
            None,
        )
        if match is not None and match not in resolved:
            resolved.append(match)

    if not resolved:
        resolved = [AgentSkill.STRATEGIC_PLANNING, AgentSkill.DEEP_RESEARCH]
    elif len(resolved) == 1:
        fallback = AgentSkill.STRATEGIC_PLANNING
        if resolved[0] == fallback:
            fallback = AgentSkill.DEEP_RESEARCH
        resolved.append(fallback)

    return resolved[:3]


# ---------------------------------------------------------------------------
# モデル構築ヘルパ
# ---------------------------------------------------------------------------


def _build_agent(spec: Dict[str, Any] | None, *, default_name: str) -> SpecialistAgent:
    spec = spec or {}
    return SpecialistAgent(
        name=str(spec.get("name") or default_name),
        skills=_resolve_skills(spec.get("skills")),
        description=str(spec.get("description") or ""),
    )


def _build_team(spec: Dict[str, Any], division_type: DivisionType) -> Team:
    team = Team(
        name=str(spec.get("name") or "New Team"),
        division_type=division_type,
        mission=str(spec.get("mission") or ""),
    )
    agent_specs = spec.get("agents") or []
    if not agent_specs:
        team.agents.append(_build_agent(None, default_name=f"{team.name} Specialist"))
    else:
        for index, agent_spec in enumerate(agent_specs):
            team.agents.append(
                _build_agent(agent_spec, default_name=f"{team.name} Specialist {index + 1}")
            )
    return team


def _build_division(spec: Dict[str, Any]) -> Division:
    division_type = _resolve_division_type(spec.get("type") or spec.get("division_type"))
    division = Division(
        name=str(spec.get("name") or "New Division"),
        type=division_type,
        mission=str(spec.get("mission") or ""),
    )
    team_specs = spec.get("teams") or []
    if not team_specs:
        division.add_team(_build_team({"name": f"{division.name} Team"}, division_type))
    else:
        for team_spec in team_specs:
            division.add_team(_build_team(team_spec, division_type))
    return division


def _division_names(org: Organization) -> set[str]:
    return {d.name.strip().lower() for d in org.divisions}


def _find_division(org: Organization, name: str | None) -> Optional[Division]:
    target = (name or "").strip().lower()
    if not target:
        return None
    return next((d for d in org.divisions if d.name.strip().lower() == target), None)


def _find_team(division: Division, name: str | None) -> Optional[Team]:
    target = (name or "").strip().lower()
    if not target:
        return None
    return next((t for t in division.teams if t.name.strip().lower() == target), None)


def _find_agent(org: Organization, name: str | None) -> Optional[SpecialistAgent]:
    target = (name or "").strip().lower()
    if not target:
        return None
    return next((a for a in org.get_all_agents() if a.name.strip().lower() == target), None)


# ---------------------------------------------------------------------------
# 純粋な組織モデル変更（I/O なし・冪等）
# ---------------------------------------------------------------------------


def apply_intervention_to_org(
    org: Organization,
    *,
    intervention_type: str,
    intervention_spec: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """対象 Organization をその場で変更し、結果サマリを返す（永続化はしない）。

    冪等性: 同名の Division/Team/Agent が既にある場合は追加せず ``applied=False`` を返す。
    SpecialistAgent.skills の 2〜3 制約は ``_resolve_skills`` で常に保証する。
    """
    spec = intervention_spec or {}
    itype = (intervention_type or "").strip()

    if itype == StructuralInterventionType.ADD_DIVISION.value:
        div_spec = spec.get("division") or spec
        name = str(div_spec.get("name") or "").strip()
        if not name:
            raise StructuralInterventionError("add_division: division.name が必要です。")
        if name.lower() in _division_names(org):
            return {"applied": False, "reason": f"Division '{name}' は既に存在します。"}
        division = _build_division(div_spec)
        org.add_division(division)
        return {
            "applied": True,
            "intervention_type": itype,
            "added_division": division.name,
            "teams_added": [t.name for t in division.teams],
            "agents_added": [a.name for t in division.teams for a in t.agents],
        }

    if itype == StructuralInterventionType.ADD_TEAM.value:
        division = _find_division(org, spec.get("division") or spec.get("division_name"))
        if division is None:
            raise StructuralInterventionError(
                f"add_team: 対象 Division '{spec.get('division')}' が見つかりません。"
            )
        team_spec = spec.get("team") or {}
        team_name = str(team_spec.get("name") or "").strip()
        if not team_name:
            raise StructuralInterventionError("add_team: team.name が必要です。")
        if _find_team(division, team_name) is not None:
            return {"applied": False, "reason": f"Team '{team_name}' は既に存在します。"}
        team = _build_team(team_spec, division.type)
        division.add_team(team)
        return {
            "applied": True,
            "intervention_type": itype,
            "division": division.name,
            "added_team": team.name,
            "agents_added": [a.name for a in team.agents],
        }

    if itype == StructuralInterventionType.ADD_AGENT.value:
        division = _find_division(org, spec.get("division") or spec.get("division_name"))
        if division is None:
            raise StructuralInterventionError(
                f"add_agent: 対象 Division '{spec.get('division')}' が見つかりません。"
            )
        team = _find_team(division, spec.get("team") or spec.get("team_name"))
        if team is None:
            raise StructuralInterventionError(
                f"add_agent: 対象 Team '{spec.get('team')}' が見つかりません。"
            )
        agent_spec = spec.get("agent") or {}
        agent_name = str(agent_spec.get("name") or "").strip()
        if not agent_name:
            raise StructuralInterventionError("add_agent: agent.name が必要です。")
        if any(a.name.strip().lower() == agent_name.lower() for a in team.agents):
            return {"applied": False, "reason": f"Agent '{agent_name}' は既に存在します。"}
        agent = _build_agent(agent_spec, default_name=agent_name)
        team.agents.append(agent)
        return {
            "applied": True,
            "intervention_type": itype,
            "division": division.name,
            "team": team.name,
            "added_agent": agent.name,
            "skills": [s.value for s in agent.skills],
        }

    if itype == StructuralInterventionType.INJECT_SKILLS.value:
        agent = _find_agent(org, spec.get("agent") or spec.get("agent_name"))
        if agent is None:
            raise StructuralInterventionError(
                f"inject_skills: 対象 Agent '{spec.get('agent')}' が見つかりません。"
            )
        requested = _resolve_skills(spec.get("skills"))
        added: List[str] = []
        skipped: List[str] = []
        for skill in requested:
            if skill in agent.skills:
                continue
            if len(agent.skills) >= 3:
                skipped.append(skill.value)
                continue
            agent.skills.append(skill)
            added.append(skill.value)
        return {
            "applied": bool(added),
            "intervention_type": itype,
            "agent": agent.name,
            "skills_added": added,
            "skills_skipped_at_cap": skipped,
            "skills_now": [s.value for s in agent.skills],
        }

    raise StructuralInterventionError(
        f"未対応の intervention_type '{intervention_type}'（対応: {', '.join(STRUCTURAL_INTERVENTION_TYPES)}）。"
    )


# ---------------------------------------------------------------------------
# 提案ビルダー（HQ プロポーザ用）
# ---------------------------------------------------------------------------


def _dedupe_key(target_org_id: str, intervention_type: str, title: str, target_ref: str) -> str:
    raw = f"{target_org_id}|{intervention_type}|{title}|{target_ref}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def build_intervention_proposal(
    *,
    target_org: Organization,
    intervention_type: str,
    title: str,
    description: str,
    intervention_spec: Dict[str, Any],
    source_org_name: str | None = None,
    target_ref: str = "",
    priority: str = "high",
) -> ImprovementProposal:
    """安定 dedupe_key / review_id 付きで cross-org 構造介入提案を組み立てる。

    同じ (target, type, title, ref) からは常に同じ dedupe_key / review_id が出るため、
    再生成をまたいだ重複排除が可能（Atlas meta 提案と同じ方式）。
    """
    dedupe_key = _dedupe_key(str(target_org.id), intervention_type, title, target_ref)
    review_id = uuid5(_REVIEW_NAMESPACE, dedupe_key)
    return ImprovementProposal(
        review_id=review_id,
        title=title,
        description=description,
        priority=priority,
        category=STRUCTURAL_INTERVENTION_CATEGORY,
        file_path="",
        is_meta=True,
        dedupe_key=dedupe_key,
        target_org_id=str(target_org.id),
        target_org_name=target_org.name,
        source_org_name=source_org_name,
        intervention_type=intervention_type,
        target_kind="org_structure",
        target_ref=target_ref,
        intervention_spec=intervention_spec,
    )


# ---------------------------------------------------------------------------
# I/O ラッパ（承認後に呼ばれる：ロード→変更→永続化）
# ---------------------------------------------------------------------------


def _as_field(proposal: ImprovementProposal | Dict[str, Any], key: str) -> Any:
    if isinstance(proposal, ImprovementProposal):
        return getattr(proposal, key, None)
    return proposal.get(key)


def _proposal_as_dict(proposal: ImprovementProposal | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(proposal, ImprovementProposal):
        return proposal.model_dump(mode="json")
    return dict(proposal)


# 構造介入 executor の capability id（routing の最終フォールバックに使う）。
STRUCTURAL_INTERVENTION_AGENT_ID = "agent:structural_intervention_executor"


async def execute_structural_intervention(
    proposal: ImprovementProposal | Dict[str, Any],
    *,
    psm: "PlatformStateManager",
    record: bool = True,
) -> Any:
    """承認済みの構造介入を **PreTaskOrchestrator 経由** で実行する（no-bypass 不変条件）。

    PreTask が分析・パターン学習を行い、構造介入 executor に委任する。ルーティングが
    （未登録レジストリ等で）executor を選べないケースに備え、最終フォールバックで
    executor id を明示する（self_improvement_loop と同じ idiom）。返り値は AgentResult。
    """
    from agents.base import AgentTask
    from core.intelligence.capability_registry import CapabilityRegistry
    from core.orchestration.orchestration_pattern_store import OrchestrationPatternStore
    from core.orchestration.pre_task_orchestrator import PreTaskOrchestrator

    registry = CapabilityRegistry(platform_home=psm.platform_home)
    try:
        if not registry.has_capability(STRUCTURAL_INTERVENTION_AGENT_ID):
            registry.scan_and_register_all()
    except Exception:  # noqa: BLE001 - スキャン不能でもフォールバックで実行できる
        pass

    store = OrchestrationPatternStore(platform_home=psm.platform_home)
    orchestrator = PreTaskOrchestrator(capability_registry=registry, pattern_store=store)

    title = _as_field(proposal, "title") or "structural intervention"
    description = f"構造介入の適用: {title}"
    analysis = orchestrator.analyze("structural_intervention", description)
    # 構造介入を正しく適用できるのは専用 executor のみ。SINGLE_AGENT パターンでは
    # recommended_agent_ids[0] だけが使われるため、executor を必ず先頭に固定する
    # （ルーティングが他エージェントを上位に出しても誤適用させない）。
    others = [
        a for a in (analysis.recommended_agent_ids or []) if a != STRUCTURAL_INTERVENTION_AGENT_ID
    ]
    analysis.recommended_agent_ids = [STRUCTURAL_INTERVENTION_AGENT_ID, *others]

    task = AgentTask(
        task_type="structural_intervention",
        description=description,
        input={
            "proposal": _proposal_as_dict(proposal),
            "platform_home": str(psm.platform_home),
        },
    )
    return await orchestrator.execute(task, analysis, record=record)


def apply_structural_intervention(
    proposal: ImprovementProposal | Dict[str, Any],
    *,
    psm: "PlatformStateManager",
) -> Dict[str, Any]:
    """承認済みの構造介入提案を対象 Organization に適用して永続化する。

    手順: 対象 org をロード → system org を拒否 → モデル変更（or 目標設定）→ 保存。
    PlatformStateManager のグローバルストア（~/.pantheon/organizations）が正準なので
    そこへ ``save_organization`` する。
    """
    target_org_id = _as_field(proposal, "target_org_id")
    target_org_name = _as_field(proposal, "target_org_name")
    intervention_type = _as_field(proposal, "intervention_type")
    intervention_spec = _as_field(proposal, "intervention_spec") or {}

    if not intervention_type:
        raise StructuralInterventionError("intervention_type が指定されていません。")

    target: Optional[Organization] = None
    if target_org_id:
        target = psm.load_organization_by_id(str(target_org_id))
    if target is None and target_org_name:
        target = psm.load_organization_by_name(str(target_org_name))
    if target is None:
        raise StructuralInterventionError(
            f"対象 Organization が見つかりません（id={target_org_id}, name={target_org_name}）。"
        )

    if target.is_system:
        raise StructuralInterventionError(
            f"system Organization '{target.name}' は構造介入の対象にできません。"
        )

    # set_goal は OrgGoalManager（platform_home/org_goals.json）に委譲。
    if intervention_type == StructuralInterventionType.SET_GOAL.value:
        from core.hierarchy.org_goals import OrgGoalManager

        description = str(
            intervention_spec.get("goal") or intervention_spec.get("description") or ""
        )
        category = str(
            intervention_spec.get("target_category")
            or intervention_spec.get("category")
            or "knowledge"
        )
        if not description:
            raise StructuralInterventionError("set_goal: goal（目標説明）が必要です。")
        goal = OrgGoalManager(platform_home=psm.platform_home).set_goal(
            org_name=target.name, description=description, target_category=category
        )
        return {
            "applied": True,
            "organization_id": str(target.id),
            "organization_name": target.name,
            "intervention_type": intervention_type,
            "goal_id": goal.goal_id,
            "goal": goal.description,
            "target_category": goal.target_category,
        }

    summary = apply_intervention_to_org(
        target, intervention_type=str(intervention_type), intervention_spec=intervention_spec
    )

    # 何も変更がなければ（冪等スキップ）保存も省く。
    if summary.get("applied"):
        from datetime import datetime, timezone

        target.last_active = datetime.now(timezone.utc)
        psm.save_organization(target)

    summary["organization_id"] = str(target.id)
    summary["organization_name"] = target.name
    return summary
