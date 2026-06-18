"""CapabilityGapResolver — turn detected gaps into agents / structural proposals.

Closes the loop that was previously open: :class:`CapabilityGapAnalyzer` only
*detected* gaps. This resolver routes each gap:

* ``agent`` / ``skill`` gap → spawn (or reuse) a :class:`SpecialistAgent` via
  :class:`DynamicAgentSpawner` and attach it to a team.
* ``team`` / ``division`` gap → emit a structural :class:`ImprovementProposal`
  that goes through :class:`PolicyEngine` with the org's
  :class:`OrgBoundaryContext`, so an **external** org can never auto-apply a
  structure change that escapes its workspace — it lands as human-required.

Nothing is force-applied: agent spawns are in-memory + registry-only, and every
Team/Division change is a proposal subject to the same Human-in-the-Loop gate as
the rest of Pantheon.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import NAMESPACE_URL, uuid5

from core.intelligence.capability_gap_analyzer import CapabilityGap
from core.models.organization import (
    AgentSkill,
    Division,
    DivisionType,
    ImprovementProposal,
    Organization,
    SpecialistAgent,
    Team,
)
from core.orchestration.dynamic_agent_spawner import DynamicAgentSpawner, SpawnRequest
from core.policy.engine import ApprovalDecision, OrgBoundaryContext, PolicyEngine

logger = logging.getLogger(__name__)

_TEAM_TYPES = {"team", "division"}
_GAP_NS = uuid5(NAMESPACE_URL, "pantheon.capability_gap")


@dataclass
class GapResolution:
    gap_id: str
    action: str  # "spawned_agent" | "proposed_team" | "proposed_division" | "skipped"
    detail: str = ""
    auto_applied: bool = False


class CapabilityGapResolver:
    def __init__(
        self,
        capability_registry=None,
        policy: Optional[PolicyEngine] = None,
        state_manager=None,
    ):
        self._spawner = DynamicAgentSpawner(capability_registry)
        self._policy = policy or PolicyEngine()
        self._sm = state_manager  # 任意: 提案を永続化する RepoStateManager

    def resolve(
        self,
        gaps: List[CapabilityGap],
        org: Organization,
    ) -> List[GapResolution]:
        """検出ギャップを順に解消する。返り値は各ギャップの処理結果。"""
        org_context = OrgBoundaryContext(
            isolation_level=getattr(org, "isolation_level", "standard"),
            allowed_path_scope=getattr(org, "allowed_path_scope", []),
        )
        results: List[GapResolution] = []
        for gap in gaps:
            if gap.implemented:
                results.append(GapResolution(gap.gap_id, "skipped", "already implemented"))
                continue
            stype = (gap.suggested_type or "").lower()
            if stype in _TEAM_TYPES:
                results.append(self._propose_structure(gap, org, org_context))
            else:
                results.append(self._spawn_agent(gap))
        return results

    # ---- agent / skill ギャップ → エージェント spawn ----
    def _spawn_agent(self, gap: CapabilityGap) -> GapResolution:
        skills = _gap_skills(gap)
        result = self._spawner.spawn(
            SpawnRequest(
                required_skills=skills,
                purpose=gap.rationale or gap.description,
                suggested_name=_clean_name(gap.suggested_name),
            )
        )
        if result.success and result.agent is not None:
            verb = "reused" if result.was_cached else "spawned"
            return GapResolution(
                gap.gap_id, "spawned_agent", f"{verb}: {result.agent.name}", auto_applied=True
            )
        return GapResolution(gap.gap_id, "skipped", result.reason or "spawn failed")

    # ---- team / division ギャップ → 構造提案（PolicyEngine 経由）----
    def _propose_structure(
        self, gap: CapabilityGap, org: Organization, org_context: OrgBoundaryContext
    ) -> GapResolution:
        is_division = gap.suggested_type.lower() == "division"
        title = f"[能力ギャップ] {'Division' if is_division else 'Team'} 追加: {gap.suggested_name}"
        # 自組織の構造変更（cross-org 介入ではない）。intervention_type / target_org_* は
        # 「別 org を変更する」マーカーで PolicyEngine が必ず人間確認に倒すため付けない。
        # 代わりにワークスペース相対の構造マーカー file_path を与え、external 組織は
        # 境界ガード（org_boundary.out_of_scope）で正しく人間確認に倒す。
        proposal = ImprovementProposal(
            # id/review_id を gap_id から決定論的に導出する。save_improvement_proposal は
            # ファイル名 {id}.json で書くため、id を固定しないと再 --resolve のたびに別ファイルが
            # 増え、同一ギャップの構造提案が /inbox に重複して積み上がる。id を固定して上書きにする。
            id=uuid5(_GAP_NS, f"gap-structure-id:{gap.gap_id}"),
            review_id=uuid5(_GAP_NS, f"gap-structure:{gap.gap_id}"),
            priority=gap.priority or "medium",
            category="org_structure",
            title=title[:120],
            description=(
                f"{gap.description}\n\n理由: {gap.rationale}\n"
                f"提案: {org.name} に {gap.suggested_name} を追加する。"
            ),
            expected_impact=f"能力ギャップ {gap.pattern_key} の解消",
            file_path=f".pantheon/structure/{gap.gap_id}.json",
            status="proposed",
            is_meta=True,
            dedupe_key=f"gap-structure:{gap.gap_id}",
            target_kind="org_structure",
            source_org_name=org.name,
        )
        verdict = self._policy.evaluate(
            json.loads(proposal.model_dump_json()), org_context=org_context
        )
        # 構造変更は組織を実質的に変えるため、既定では人間承認ゲートを通す。
        # policy.yaml が org_structure を明示的に auto_approve する運用にした場合のみ自動適用。
        auto = verdict.decision == ApprovalDecision.AUTO_APPROVE
        if auto:
            self._apply_structure(org, gap, is_division)
            proposal.status = "done"
        else:
            proposal.status = "pending"
        if self._sm is not None:
            try:
                self._sm.save_improvement_proposal(proposal)
            except Exception as exc:  # noqa: BLE001
                logger.warning("failed to persist structure proposal %s: %s", gap.gap_id, exc)
        return GapResolution(
            gap.gap_id,
            "proposed_division" if is_division else "proposed_team",
            f"decision={verdict.decision.value} rule={verdict.rule_name}",
            auto_applied=auto,
        )

    def _resolve_min_two_skills(self, gap: CapabilityGap) -> List[AgentSkill]:
        """SpecialistAgent の 2〜3 スキル制約を満たすスキルセットを返す。"""
        skills = self._spawner._resolve_skills(_gap_skills(gap))
        for filler in (AgentSkill.DEEP_RESEARCH, AgentSkill.KNOWLEDGE_CURATION):
            if len(skills) >= 2:
                break
            if filler not in skills:
                skills.append(filler)
        return skills[:3]

    def _apply_structure(self, org: Organization, gap: CapabilityGap, is_division: bool) -> None:
        agent = SpecialistAgent(
            name=f"{gap.suggested_name} Lead",
            skills=self._resolve_min_two_skills(gap),
            description=gap.rationale[:100],
        )
        dtype = DivisionType.ORG_EVOLUTION
        team = Team(
            name=str(gap.suggested_name),
            division_type=dtype,
            agents=[agent],
            mission=gap.description[:200],
        )
        if is_division:
            division = Division(name=str(gap.suggested_name), type=dtype, teams=[team])
            org.add_division(division)
        elif org.divisions:
            org.divisions[0].add_team(team)
        else:
            org.add_division(Division(name="自動生成部門", type=dtype, teams=[team]))


def _gap_skills(gap: CapabilityGap) -> List[str]:
    """ギャップ名/種別から required_skills のヒントを作る（spawner が解決・補填する）。"""
    base = (gap.suggested_name or "").lower()
    hints = [base]
    if gap.suggested_type == "skill":
        hints.append(base.replace("_", " "))
    return [h for h in hints if h]


def _clean_name(name: Optional[str]) -> Optional[str]:
    return name.strip() if isinstance(name, str) and name.strip() else None


def resolve_gaps_for_org(
    gaps: List[CapabilityGap],
    org: Organization,
    *,
    capability_registry=None,
    policy: Optional[PolicyEngine] = None,
    state_manager=None,
) -> Dict[str, Any]:
    """便宜関数: ギャップを解消し、サマリー dict を返す。"""
    resolver = CapabilityGapResolver(capability_registry, policy, state_manager)
    results = resolver.resolve(gaps, org)
    return {
        "total": len(results),
        "spawned_agents": sum(1 for r in results if r.action == "spawned_agent"),
        "proposed_teams": sum(1 for r in results if r.action == "proposed_team"),
        "proposed_divisions": sum(1 for r in results if r.action == "proposed_division"),
        "auto_applied": sum(1 for r in results if r.auto_applied),
        # 実際に充足したギャップの id。能力が registry に存在するようになった spawn（新規/再利用）と、
        # auto-apply された構造変更だけが「満たされた」。HITL 提案止まり（auto_applied=False）や spawn
        # 失敗（skipped）は未充足なので含めない＝呼び出し側が implemented にマークすると過剰畳み込みになる。
        # これを CapabilityGapAnalyzer.mark_implemented に渡すと、検出済みギャップが解消後も active のまま
        # 残り over-report する drift（充足済みを自動 implemented にしない既知 issue）が閉じる。
        "satisfied_gap_ids": [
            r.gap_id
            for r in results
            if r.action == "spawned_agent"
            or (r.auto_applied and r.action in ("proposed_team", "proposed_division"))
        ],
        "results": [r.__dict__ for r in results],
    }
