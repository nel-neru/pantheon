"""
SkillPropagator — スキル継承 (A-07)
高パフォーマンスエージェントの成功パターンを他エージェントに共有する
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from core.intelligence.agent_knowledge import AgentKnowledgeAccumulator, SuccessPattern
from core.intelligence.skill_proficiency import SkillProficiencyManager


class SkillPropagator:
    """高習熟度エージェントの成功パターンを他エージェントへ伝播する。"""

    def __init__(self, proficiency_manager=None, knowledge_accumulator=None):
        self.proficiency_manager = proficiency_manager or SkillProficiencyManager()
        self.knowledge_accumulator = knowledge_accumulator or AgentKnowledgeAccumulator()

    def identify_top_agents(self, skill_name: str, min_proficiency: float = 70.0) -> list[str]:
        data = self.proficiency_manager._load()
        ranked = []
        for agent_id, skills in data.items():
            proficiency = float(skills.get(skill_name, {}).get("proficiency", 0.0))
            if proficiency >= min_proficiency:
                ranked.append((agent_id, proficiency))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return [agent_id for agent_id, _ in ranked]

    def propagate(self, from_agent_id: str, to_agent_id: str, skill_name: str) -> bool:
        source_patterns = [
            pattern
            for pattern in self.knowledge_accumulator._load_patterns()
            if pattern.agent_id == from_agent_id and pattern.skill_name == skill_name
        ]
        if not source_patterns:
            return False

        for pattern in source_patterns:
            cloned_pattern = SuccessPattern(
                pattern_id=str(uuid4()),
                agent_id=to_agent_id,
                skill_name=skill_name,
                task_type=pattern.task_type,
                pattern_summary=f"[継承元: {from_agent_id}] {pattern.pattern_summary}",
                success_score=pattern.success_score,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self.knowledge_accumulator._append_pattern(cloned_pattern)

            if self.knowledge_accumulator.knowledge_manager is not None:
                self.knowledge_accumulator.knowledge_manager.save_insight(
                    title=f"[{to_agent_id}] propagated {skill_name} pattern",
                    content=cloned_pattern.pattern_summary,
                    tags=["propagated_pattern", skill_name, pattern.task_type, to_agent_id],
                    source_org=to_agent_id,
                    importance="medium",
                )

        return True

    def auto_propagate_top_patterns(self, skill_name: str, top_n: int = 3) -> int:
        data = self.proficiency_manager._load()
        top_agents = self.identify_top_agents(skill_name)[:top_n]
        target_agents = [agent_id for agent_id, skills in data.items() if skill_name in skills]

        propagations = 0
        for from_agent_id in top_agents:
            for to_agent_id in target_agents:
                if from_agent_id == to_agent_id:
                    continue
                if self.propagate(from_agent_id, to_agent_id, skill_name):
                    propagations += 1
        return propagations
