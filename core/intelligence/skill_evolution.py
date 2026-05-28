"""
SkillEvolutionEngine — 新AgentSkill自動定義 (H-06)
タスクパターンを分析し新スキルを提案する
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from core.models.organization import AgentSkill


@dataclass
class SkillDefinitionProposal:
    skill_name: str
    description: str
    triggered_by: list[str]
    use_case: str
    proposed_at: str


class SkillEvolutionEngine:
    PATTERN_SKILL_MAP: dict[str, SkillDefinitionProposal] = {
        "security_audit": SkillDefinitionProposal(
            skill_name="SECURITY_AUDIT",
            description="セキュリティ監査専門スキル",
            triggered_by=["security_audit", "security", "vulnerability_review"],
            use_case="脆弱性診断や安全性レビューを高頻度で行うケース",
            proposed_at="",
        ),
        "dependency_analysis": SkillDefinitionProposal(
            skill_name="DEPENDENCY_ANALYSIS",
            description="依存関係分析スキル",
            triggered_by=["dependency_analysis", "dependency_update", "impact_analysis"],
            use_case="依存関係の変更影響や構造分析を継続的に行うケース",
            proposed_at="",
        ),
    }

    def __init__(self):
        self._proposed_skills: list[SkillDefinitionProposal] = []

    def analyze_task_patterns(self, task_history: list[dict]) -> list[SkillDefinitionProposal]:
        proposals: list[SkillDefinitionProposal] = []
        existing_skills = {skill.value.upper() for skill in AgentSkill}

        for item in task_history:
            task_type = str(item.get("task_type") or item.get("category") or "")
            frequency = int(item.get("frequency") or 0)
            if frequency < 5 or not task_type:
                continue

            template = self.PATTERN_SKILL_MAP.get(task_type)
            if template:
                if template.skill_name in existing_skills:
                    continue
                proposals.append(
                    SkillDefinitionProposal(
                        skill_name=template.skill_name,
                        description=template.description,
                        triggered_by=list(template.triggered_by),
                        use_case=template.use_case,
                        proposed_at=datetime.now(timezone.utc).isoformat(),
                    )
                )
                continue

            generated_name = task_type.upper()
            if generated_name in existing_skills:
                continue
            proposals.append(
                SkillDefinitionProposal(
                    skill_name=generated_name,
                    description=f"{task_type} 専門スキル",
                    triggered_by=[task_type],
                    use_case=f"{task_type} 系タスクが高頻度で発生するケース",
                    proposed_at=datetime.now(timezone.utc).isoformat(),
                )
            )

        self._proposed_skills = proposals
        return proposals

    def get_proposed_skills(self) -> list[SkillDefinitionProposal]:
        return list(self._proposed_skills)
