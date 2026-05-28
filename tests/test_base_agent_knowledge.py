"""Unit tests for BaseAgent knowledge integration"""

import pytest

from agents.base import AgentResult, AgentTask, BaseAgent
from core.knowledge.manager import KnowledgeManager
from core.models.organization import AgentSkill, SpecialistAgent


class DummySkillEngine:
    def __init__(self):
        self.calls = []

    def apply_skills_to_prompt(self, base_prompt, skills):
        self.calls.append((base_prompt, list(skills)))
        return "patched prompt"


class DummyAgent(BaseAgent):
    async def run(self, task: AgentTask) -> AgentResult:
        return AgentResult(success=True)


@pytest.fixture

def specialist():
    return SpecialistAgent(
        name="KnowledgeAgent",
        skills=[AgentSkill.DEEP_RESEARCH, AgentSkill.TOOL_INTEGRATION],
    )


@pytest.fixture

def agent(specialist):
    return DummyAgent(specialist)


class TestBaseAgentKnowledge:
    def test_apply_skills_to_prompt_calls_skill_engine(self, agent):
        engine = DummySkillEngine()
        agent._skill_engine = engine

        prompt = agent.apply_skills_to_prompt("Base prompt")

        assert prompt == "patched prompt"
        assert engine.calls == [(
            "Base prompt",
            [AgentSkill.DEEP_RESEARCH, AgentSkill.TOOL_INTEGRATION],
        )]

    def test_get_skill_tags_returns_skill_values_as_strings(self, agent):
        assert agent.get_skill_tags() == ["deep_research", "tool_integration"]

    def test_enrich_with_knowledge_returns_context_when_entries_exist(self, agent, tmp_path):
        manager = KnowledgeManager(tmp_path)
        manager.save_insight(
            "Root cause analysis",
            "Capture evidence before proposing changes.",
            tags=["deep_research"],
        )

        context = agent._enrich_with_knowledge(manager)

        assert "Root cause analysis" in context
        assert "Capture evidence before proposing changes." in context

    def test_save_execution_knowledge_saves_entry_on_success(self, agent, tmp_path):
        manager = KnowledgeManager(tmp_path)
        task = AgentTask(task_type="review", description="Inspect the repository")
        result = AgentResult(
            success=True,
            thinking_process="Found a useful pattern",
            execution_log="Saved actionable notes",
        )

        insight_id = agent._save_execution_knowledge(
            manager,
            result,
            task,
            extra_tags=["code_review"],
        )
        insights = manager.get_insights()

        assert insight_id is not None
        assert len(insights) == 1
        assert insights[0]["source_org"] == "KnowledgeAgent"
        assert "deep_research" in insights[0]["tags"]
        assert "tool_integration" in insights[0]["tags"]
        assert "code_review" in insights[0]["tags"]
        assert "Inspect the repository" in insights[0]["content"]

    def test_save_execution_knowledge_does_not_save_on_failure(self, agent, tmp_path):
        manager = KnowledgeManager(tmp_path)
        task = AgentTask(task_type="review", description="Inspect the repository")
        result = AgentResult(success=False, error="LLM failed")

        insight_id = agent._save_execution_knowledge(manager, result, task)

        assert insight_id is None
        assert manager.count() == 0
