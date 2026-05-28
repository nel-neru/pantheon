"""
DynamicAgentSpawner — タスク要件に応じた動的エージェント作成 (N-04)

既存エージェントがタスク要件を満たさない場合に、
最適なスキルセットを持つ新しい SpecialistAgent を動的に作成する。

これにより「必要な能力が存在しないなら作る」という
自律的能力拡張が実現する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import uuid4

from core.models.organization import AgentSkill, SpecialistAgent

logger = logging.getLogger(__name__)


@dataclass
class SpawnRequest:
    """新エージェント作成リクエスト。"""
    required_skills: List[str]           # AgentSkill.value のリスト
    purpose: str                         # なぜこのエージェントが必要か
    task_type: str = ""
    suggested_name: Optional[str] = None


@dataclass
class SpawnResult:
    """エージェント作成結果。"""
    success: bool
    agent: Optional[SpecialistAgent] = None
    reason: str = ""
    was_cached: bool = False             # 既存エージェントを再利用した場合


class DynamicAgentSpawner:
    """
    タスク要件に基づいてエージェントを動的に作成・再利用する。

    スポーン戦略:
    1. CapabilityRegistry に要件を満たすエージェントが存在する → 再利用
    2. 既存スキルの組み合わせで作れる → 新規作成
    3. 要件が AgentSkill enum に存在しない → 最近傍スキルで代替
    """

    # スキル名 → AgentSkill のマッピング（ファジーマッチ用）
    SKILL_ALIASES: Dict[str, AgentSkill] = {
        "research": AgentSkill.DEEP_RESEARCH,
        "search": AgentSkill.DEEP_RESEARCH,
        "investigate": AgentSkill.DEEP_RESEARCH,
        "code": AgentSkill.CODEBASE_EXPLORATION,
        "explore": AgentSkill.CODEBASE_EXPLORATION,
        "scan": AgentSkill.CODEBASE_EXPLORATION,
        "security": AgentSkill.TOOL_INTEGRATION,
        "api": AgentSkill.TOOL_INTEGRATION,
        "strategy": AgentSkill.STRATEGIC_PLANNING,
        "plan": AgentSkill.STRATEGIC_PLANNING,
        "performance": AgentSkill.PERFORMANCE_ANALYSIS,
        "optimize": AgentSkill.PERFORMANCE_ANALYSIS,
        "knowledge": AgentSkill.KNOWLEDGE_CURATION,
        "docs": AgentSkill.KNOWLEDGE_CURATION,
        "prompt": AgentSkill.PROMPT_ENGINEERING,
        "llm": AgentSkill.PROMPT_ENGINEERING,
        "org": AgentSkill.ORG_DESIGN,
        "design": AgentSkill.ORG_DESIGN,
        "workflow": AgentSkill.AGENT_WORKFLOW_DESIGN,
        "langgraph": AgentSkill.AGENT_WORKFLOW_DESIGN,
    }

    def __init__(self, capability_registry=None):
        self._registry = capability_registry
        self._spawned_agents: List[SpecialistAgent] = []

    def spawn(self, request: SpawnRequest) -> SpawnResult:
        """
        スポーンリクエストに基づいてエージェントを作成または再利用する。
        """
        # Step 1: 既存エージェントで要件を満たせるか確認
        if self._registry:
            existing = self._find_existing_agent(request.required_skills)
            if existing:
                logger.info("DynamicAgentSpawner: reusing existing agent %s", existing.id)
                return SpawnResult(success=True, agent=existing, was_cached=True)

        # Step 2: 要件スキルを AgentSkill に解決
        resolved_skills = self._resolve_skills(request.required_skills)
        if len(resolved_skills) < 2:
            # SpecialistAgent は最低2スキル必要 → デフォルトスキルを追加
            default_fallback = AgentSkill.DEEP_RESEARCH
            if default_fallback not in resolved_skills:
                resolved_skills.append(default_fallback)

        # Step 3: 新エージェントを作成
        name = request.suggested_name or self._generate_agent_name(resolved_skills)
        agent = SpecialistAgent(
            name=name,
            skills=resolved_skills[:3],  # max 3
            description=f"動的作成エージェント: {request.purpose[:100]}",
        )
        self._spawned_agents.append(agent)

        # Step 4: CapabilityRegistry に登録
        if self._registry:
            from core.intelligence.capability_registry import CapabilityEntry
            self._registry.register(CapabilityEntry(
                id=f"agent:dynamic:{agent.id}",
                name=agent.name,
                capability_type="agent",
                description=agent.description,
                skills=[s.value for s in agent.skills],
            ))

        logger.info(
            "DynamicAgentSpawner: spawned new agent %s with skills %s",
            agent.name, [s.value for s in agent.skills],
        )
        return SpawnResult(success=True, agent=agent, was_cached=False,
                           reason=f"New agent created with skills: {[s.value for s in agent.skills]}")

    def get_spawned_agents(self) -> List[SpecialistAgent]:
        """このセッションで作成されたエージェントのリストを返す。"""
        return list(self._spawned_agents)

    def _find_existing_agent(self, required_skills: List[str]) -> Optional[SpecialistAgent]:
        """既存エージェントの中でスキル要件を最もよく満たすものを返す。"""
        if not self._registry:
            return None
        agents = self._registry.list_agents()
        required_set = set(required_skills)
        for entry in agents:
            entry_skills = set(entry.skills)
            if required_set.issubset(entry_skills) or len(required_set & entry_skills) >= 2:
                # 既存エントリから SpecialistAgent を再構築
                try:
                    resolved = self._resolve_skills(list(entry.skills))
                    if len(resolved) >= 2:
                        return SpecialistAgent(
                            name=entry.name,
                            skills=resolved[:3],
                            description=entry.description,
                        )
                except Exception:
                    continue
        return None

    def _resolve_skills(self, skill_names: List[str]) -> List[AgentSkill]:
        """スキル名のリストを AgentSkill enum に解決する。"""
        resolved = []
        for name in skill_names:
            skill = self._name_to_skill(name)
            if skill and skill not in resolved:
                resolved.append(skill)
        return resolved

    def _name_to_skill(self, name: str) -> Optional[AgentSkill]:
        """スキル名（文字列）を AgentSkill に変換する。ファジーマッチ対応。"""
        # 完全一致
        try:
            return AgentSkill(name)
        except ValueError:
            pass
        # エイリアス一致
        name_lower = name.lower()
        if name_lower in self.SKILL_ALIASES:
            return self.SKILL_ALIASES[name_lower]
        # 部分一致
        for alias, skill in self.SKILL_ALIASES.items():
            if alias in name_lower or name_lower in alias:
                return skill
        return None

    def _generate_agent_name(self, skills: List[AgentSkill]) -> str:
        """スキルセットからエージェント名を自動生成する。"""
        if not skills:
            return f"DynamicAgent_{uuid4().hex[:6]}"
        primary = skills[0].value.replace("_", " ").title().replace(" ", "")
        return f"{primary}Specialist"
