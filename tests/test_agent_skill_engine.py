"""Unit tests for AgentSkillEngine"""

from core.intelligence.agent_skill_engine import AgentSkillEngine
from core.models.organization import AgentSkill


class TestAgentSkillEngine:
    def test_apply_skills_to_prompt_includes_base_and_skill_text(self):
        engine = AgentSkillEngine()
        base_prompt = "Base prompt"

        prompt = engine.apply_skills_to_prompt(
            base_prompt,
            [AgentSkill.STRATEGIC_PLANNING],
        )

        assert base_prompt in prompt
        assert "長期戦略を立案するビジョナリーなアーキテクト" in prompt

    def test_apply_multiple_skills_includes_each_skill_text(self):
        engine = AgentSkillEngine()

        prompt = engine.apply_skills_to_prompt(
            "Base prompt",
            [AgentSkill.STRATEGIC_PLANNING, AgentSkill.DEEP_RESEARCH],
        )

        assert "長期戦略を立案するビジョナリーなアーキテクト" in prompt
        assert "詳細な技術調査と根本原因分析の専門家" in prompt

    def test_empty_skills_returns_base_prompt_unchanged(self):
        engine = AgentSkillEngine()
        base_prompt = "Base prompt"

        assert engine.apply_skills_to_prompt(base_prompt, []) == base_prompt

    def test_get_skill_tags_returns_skill_values(self):
        engine = AgentSkillEngine()

        assert engine.get_skill_tags([AgentSkill.DEEP_RESEARCH]) == ["deep_research"]

    def test_describe_agent_returns_non_empty_string(self):
        engine = AgentSkillEngine()

        description = engine.describe_agent([AgentSkill.PERFORMANCE_ANALYSIS])

        assert isinstance(description, str)
        assert description.strip()
