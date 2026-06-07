"""
TaskRouter — タスクを最適なエージェントへルーティング (N-02)

タスクの種別・複雑度・コンテキストを分析し、
CapabilityRegistry の現有エージェントの中から
最適なエージェント（or エージェント群）を選択する。

実行前メタ分析の第2ステップ。
PreTaskOrchestrator が analyze() の中でこれを呼び出す。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from core.models.organization import AgentSkill

logger = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    """ルーティング判定結果。"""

    selected_agent_ids: List[str]
    routing_reason: str
    skill_match_scores: Dict[str, float] = field(default_factory=dict)  # agent_id → score
    fallback_used: bool = False


# タスク種別 → 必要スキルセット（重み付き）
TASK_SKILL_REQUIREMENTS: Dict[str, List[Tuple[AgentSkill, float]]] = {
    "code_review": [
        (AgentSkill.CODEBASE_EXPLORATION, 0.9),
        (AgentSkill.PERFORMANCE_ANALYSIS, 0.7),
        (AgentSkill.TOOL_INTEGRATION, 0.6),
        (AgentSkill.DEEP_RESEARCH, 0.4),
    ],
    "improvement_execution": [
        (AgentSkill.PROMPT_ENGINEERING, 0.8),
        (AgentSkill.TOOL_INTEGRATION, 0.8),
        (AgentSkill.AGENT_WORKFLOW_DESIGN, 0.5),
    ],
    "codebase_exploration": [
        (AgentSkill.CODEBASE_EXPLORATION, 1.0),
        (AgentSkill.DEEP_RESEARCH, 0.7),
    ],
    "meta_improvement": [
        (AgentSkill.STRATEGIC_PLANNING, 0.9),
        (AgentSkill.AGENT_WORKFLOW_DESIGN, 0.8),
        (AgentSkill.PERFORMANCE_ANALYSIS, 0.6),
    ],
    "security_audit": [
        (AgentSkill.TOOL_INTEGRATION, 0.9),
        (AgentSkill.DEEP_RESEARCH, 0.8),
    ],
    "knowledge_curation": [
        (AgentSkill.KNOWLEDGE_CURATION, 1.0),
        (AgentSkill.DEEP_RESEARCH, 0.5),
    ],
    "organization_design": [
        (AgentSkill.ORG_DESIGN, 0.9),
        (AgentSkill.STRATEGIC_PLANNING, 0.8),
    ],
    "prompt_optimization": [
        (AgentSkill.PROMPT_ENGINEERING, 1.0),
        (AgentSkill.KNOWLEDGE_CURATION, 0.5),
    ],
    "performance_analysis": [
        (AgentSkill.PERFORMANCE_ANALYSIS, 1.0),
        (AgentSkill.DEEP_RESEARCH, 0.6),
    ],
    "structural_intervention": [
        (AgentSkill.ORG_DESIGN, 0.95),
        (AgentSkill.AGENT_WORKFLOW_DESIGN, 0.85),
        (AgentSkill.STRATEGIC_PLANNING, 0.5),
    ],
}


class TaskRouter:
    """
    タスク種別と CapabilityRegistry を照合して最適エージェントを選択する。

    選択アルゴリズム:
    1. タスク種別から必要スキルセット（重み付き）を取得
    2. 各エージェントのスキルマッチスコアを計算
    3. スコア上位エージェントを返す
    4. スコアが低い場合は DynamicAgentSpawner に委譲することをフラグする
    """

    SPAWN_THRESHOLD = 0.3  # このスコア以下なら新エージェント作成を推奨

    def __init__(self, capability_registry=None):
        self._registry = capability_registry

    def route(
        self,
        task_type: str,
        max_agents: int = 2,
        require_spawn_if_low: bool = True,
    ) -> RoutingDecision:
        """
        タスク種別に最適なエージェントを選択する。

        Args:
            task_type: タスクの種別
            max_agents: 最大エージェント数
            require_spawn_if_low: スコアが低い場合にスポーンフラグを立てるか

        Returns:
            RoutingDecision
        """
        requirements = TASK_SKILL_REQUIREMENTS.get(task_type, [])

        if not self._registry or not requirements:
            return RoutingDecision(
                selected_agent_ids=[],
                routing_reason=f"No routing requirements defined for task_type={task_type}",
                fallback_used=True,
            )

        agents = self._registry.list_agents()
        if not agents:
            return RoutingDecision(
                selected_agent_ids=[],
                routing_reason="No agents registered in CapabilityRegistry",
                fallback_used=True,
            )

        # スコア計算
        scores: Dict[str, float] = {}
        for agent_entry in agents:
            agent_skills = set(agent_entry.skills)
            score = 0.0
            for skill, weight in requirements:
                if skill.value in agent_skills:
                    score += weight
            # 使用実績ボーナス（よく使われるエージェントをわずかに優先）
            usage_bonus = min(0.1, agent_entry.usage_count * 0.01)
            scores[agent_entry.id] = round(score + usage_bonus, 3)

        # スコア降順でソート
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_agents = [(aid, score) for aid, score in ranked if score > 0][:max_agents]

        if not top_agents:
            return RoutingDecision(
                selected_agent_ids=[],
                routing_reason=f"No agents match skill requirements for {task_type}",
                skill_match_scores=scores,
                fallback_used=True,
            )

        best_score = top_agents[0][1]
        max_possible = sum(w for _, w in requirements)
        normalized_score = best_score / max_possible if max_possible > 0 else 0

        reason_parts = [
            f"タスク '{task_type}' に対して最適エージェントを選択",
            f"マッチスコア: {normalized_score:.1%}",
        ]

        if normalized_score < self.SPAWN_THRESHOLD and require_spawn_if_low:
            reason_parts.append(
                f"スコアが低いため ({normalized_score:.1%} < {self.SPAWN_THRESHOLD:.1%}) "
                f"新エージェント作成を推奨"
            )

        return RoutingDecision(
            selected_agent_ids=[aid for aid, _ in top_agents],
            routing_reason="。".join(reason_parts),
            skill_match_scores={aid: score for aid, score in ranked},
            fallback_used=normalized_score < self.SPAWN_THRESHOLD,
        )

    def get_task_type_capabilities(self) -> Dict[str, List[str]]:
        """タスク種別 → 必要スキルのマッピングを返す（デバッグ/表示用）。"""
        return {
            task_type: [skill.value for skill, _ in requirements]
            for task_type, requirements in TASK_SKILL_REQUIREMENTS.items()
        }


class LoadBalancer:
    """In-memory agent load tracker."""

    def __init__(self, max_tasks_per_agent: int = 10):
        self.max_tasks_per_agent = max_tasks_per_agent
        self._loads: Dict[str, int] = {}

    def record_task_start(self, agent_id: str) -> None:
        self._loads[agent_id] = self.get_load(agent_id) + 1

    def record_task_end(self, agent_id: str) -> None:
        self._loads[agent_id] = max(0, self.get_load(agent_id) - 1)

    def get_load(self, agent_id: str) -> int:
        return int(self._loads.get(agent_id, 0))

    def is_overloaded(self, agent_id: str) -> bool:
        return self.get_load(agent_id) >= self.max_tasks_per_agent

    def get_least_loaded(self, agent_ids: list[str]) -> str:
        if not agent_ids:
            return ""
        return min(agent_ids, key=lambda agent_id: (self.get_load(agent_id), agent_id))
