"""
tests/test_agent_factory.py

AgentFactory と GenericSkillAgent の動作検証テスト。

- AgentFactory がスキルから正しい Python クラスを選択すること
- スキルが違うと GenericSkillAgent のシステムプロンプトが変わること
- CapabilityRegistry がスキル情報を正しく保持すること
- PreTaskOrchestrator がデフォルト factory を自動生成すること
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agents.agent_factory import AgentFactory, _skills_from_ids
from agents.base import AgentResult, AgentTask
from agents.generic_skill_agent import GenericSkillAgent
from core.models.organization import AgentSkill, SpecialistAgent


# ────────────────────────────────────────────────────────────────────────────
# AgentFactory.create
# ────────────────────────────────────────────────────────────────────────────


class TestAgentFactoryCreate:
    def test_creates_code_review_agent(self):
        """code_reviewer YAML の implementation で CodeReviewAgent クラスが使われる。"""
        factory = AgentFactory()
        agent = factory.create("agent:code_reviewer")
        assert agent is not None
        from agents.code_review_agent import CodeReviewAgent

        assert isinstance(agent, CodeReviewAgent)

    def test_creates_codebase_explorer_agent(self):
        factory = AgentFactory()
        agent = factory.create("agent:codebase_explorer")
        assert agent is not None
        from agents.codebase_explorer_agent import CodebaseExplorerAgent

        assert isinstance(agent, CodebaseExplorerAgent)

    def test_creates_generic_skill_agent_for_strategic_planner(self):
        """strategic_planner は GenericSkillAgent で実装される。"""
        factory = AgentFactory()
        agent = factory.create("agent:strategic_planner")
        assert agent is not None
        assert isinstance(agent, GenericSkillAgent)

    def test_strategic_planner_has_correct_skills(self):
        factory = AgentFactory()
        agent = factory.create("agent:strategic_planner")
        assert AgentSkill.STRATEGIC_PLANNING in agent.skills
        assert AgentSkill.ORG_DESIGN in agent.skills

    def test_knowledge_curator_has_correct_skills(self):
        factory = AgentFactory()
        agent = factory.create("agent:knowledge_curator")
        assert AgentSkill.KNOWLEDGE_CURATION in agent.skills
        assert AgentSkill.DEEP_RESEARCH in agent.skills

    def test_unknown_id_returns_none(self):
        factory = AgentFactory()
        agent = factory.create("agent:nonexistent_agent_xyz")
        assert agent is None

    def test_unknown_skill_ids_log_warning_and_use_fallbacks(self, caplog):
        caplog.set_level("WARNING")
        skills = _skills_from_ids(["unknown_skill", AgentSkill.STRATEGIC_PLANNING.value])

        assert AgentSkill.STRATEGIC_PLANNING in skills
        assert len(skills) >= 2
        assert "unknown skill ids" in caplog.text
        assert "unknown_skill" in caplog.text

    def test_quality_guardian_preserves_custom_skill_tags(self):
        factory = AgentFactory()
        agent = factory.create("agent:quality_guardian")
        assert agent is not None
        assert isinstance(agent, GenericSkillAgent)
        assert agent.get_skill_tags()[:2] == ["quality_guardian", "code_review"]

    def test_all_registered_agents_can_be_instantiated(self):
        """レジストリの全エントリがインスタンス化できること。"""
        factory = AgentFactory()
        for cap_id in factory.all_capability_ids():
            agent = factory.create(cap_id)
            assert agent is not None, f"Failed to create agent for {cap_id}"

    def test_yaml_agent_prompt_preserves_base_prompt(self, monkeypatch):
        factory = AgentFactory()
        defn = SimpleNamespace(
            name="YamlAgent",
            description="desc",
            skills=[AgentSkill.STRATEGIC_PLANNING.value, AgentSkill.DEEP_RESEARCH.value],
            implementation="",
            build_system_prompt=lambda _loader: "YAML_PROMPT",
        )
        monkeypatch.setattr(factory, "_get_agent_loader", lambda: SimpleNamespace(get=lambda _capability_id: defn))
        monkeypatch.setattr(factory, "_get_skill_loader", lambda: object())

        agent = factory.create("agent:yaml_agent")

        assert agent is not None
        prompt = agent.apply_skills_to_prompt("BASE_PROMPT")
        assert "BASE_PROMPT" in prompt
        assert "YAML_PROMPT" in prompt


# ────────────────────────────────────────────────────────────────────────────
# AgentFactory.create_for_skills
# ────────────────────────────────────────────────────────────────────────────


class TestAgentFactoryCreateForSkills:
    def test_exact_match_returns_dedicated_agent(self):
        """完全一致するスキルセットには専用エージェントが返る。"""
        factory = AgentFactory()
        agent = factory.create_for_skills(
            [AgentSkill.CODEBASE_EXPLORATION, AgentSkill.DEEP_RESEARCH]
        )
        from agents.codebase_explorer_agent import CodebaseExplorerAgent

        assert isinstance(agent, CodebaseExplorerAgent)
    def test_unknown_skills_returns_generic(self):
        """未登録のスキル組み合わせは GenericSkillAgent が返る。
        CORPORATE_RESEARCH + PROMPT_ENGINEERING は部分一致候補があるが
        overlap が 1/2 未満なので GenericSkillAgent にフォールバックする。"""
        factory = AgentFactory()
        # CORPORATE_RESEARCH はどのエージェントも持っていない→ overlap < 2 → Generic
        agent = factory.create_for_skills(
            [AgentSkill.CORPORATE_RESEARCH, AgentSkill.ORG_DESIGN]
        )
        assert isinstance(agent, GenericSkillAgent)

    def test_single_skill_gets_deep_research_appended(self):
        """スキルが1個の場合 DEEP_RESEARCH が補完されてエラーにならない。"""
        factory = AgentFactory()
        agent = factory.create_for_skills([AgentSkill.STRATEGIC_PLANNING])
        assert agent is not None
        assert len(agent.skills) >= 2


# ────────────────────────────────────────────────────────────────────────────
# GenericSkillAgent — スキルによる差分
# ────────────────────────────────────────────────────────────────────────────


class TestGenericSkillAgentSkillDifference:
    """スキルが異なると apply_skills_to_prompt が返すプロンプトが変わることを確認。"""

    def test_strategic_planner_prompt_differs_from_knowledge_curator(self):
        planner = GenericSkillAgent.from_skills(
            [AgentSkill.STRATEGIC_PLANNING, AgentSkill.ORG_DESIGN]
        )
        curator = GenericSkillAgent.from_skills(
            [AgentSkill.KNOWLEDGE_CURATION, AgentSkill.DEEP_RESEARCH]
        )
        planner_prompt = planner.apply_skills_to_prompt("BASE")
        curator_prompt = curator.apply_skills_to_prompt("BASE")
        assert planner_prompt != curator_prompt

    def test_skill_keywords_appear_in_prompt(self):
        """AgentSkillEngine が注入するスキル定義がプロンプトに含まれる。"""
        agent = GenericSkillAgent.from_skills(
            [AgentSkill.PERFORMANCE_ANALYSIS, AgentSkill.DEEP_RESEARCH]
        )
        prompt = agent.apply_skills_to_prompt("BASE_PROMPT")
        # PERFORMANCE_ANALYSIS のペルソナ文字列が含まれているはず
        assert "パフォーマンス" in prompt or "performance" in prompt.lower()

    def test_result_contains_skill_names(self):
        agent = GenericSkillAgent.from_skills(
            [AgentSkill.CORPORATE_RESEARCH, AgentSkill.DEEP_RESEARCH],
        )
        task = AgentTask("research", "市場調査を行え")
        result = asyncio.run(agent.run(task))
        assert result.success
        assert "corporate_research" in result.output["result"] or \
               "corporate_research" in result.thinking_process

    def test_generic_agent_without_llm(self):
        agent = GenericSkillAgent.from_skills(
            [AgentSkill.STRATEGIC_PLANNING, AgentSkill.AGENT_WORKFLOW_DESIGN],
        )
        task = AgentTask("meta_improvement", "システム改善計画を立案せよ")
        result = asyncio.run(agent.run(task))
        assert result.success
        assert result.output["confidence"] > 0


# ────────────────────────────────────────────────────────────────────────────
# CapabilityRegistry — スキルが正しく登録されること
# ────────────────────────────────────────────────────────────────────────────


class TestCapabilityRegistryWithSkills:
    def test_scan_registers_agents_with_skills(self, tmp_path):
        from core.intelligence.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry(
            platform_home=tmp_path,
            registry_file=tmp_path / "reg.json",
        )
        import pathlib

        repo_root = pathlib.Path(__file__).parent.parent
        registry.scan_and_register_all(repo_root=repo_root)

        # code_reviewer がスキルを持っていること（新IDはYAMLのstem）
        cap = registry.get("agent:code_reviewer")
        assert cap is not None
        assert len(cap.skills) >= 2
        assert "codebase_exploration" in cap.skills or "performance_analysis" in cap.skills

    def test_scan_registers_virtual_agents(self, tmp_path):
        """GenericSkillAgent ベースのエージェントも登録される。"""
        from core.intelligence.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry(
            platform_home=tmp_path,
            registry_file=tmp_path / "reg.json",
        )
        import pathlib

        repo_root = pathlib.Path(__file__).parent.parent
        registry.scan_and_register_all(repo_root=repo_root)

        cap = registry.get("agent:strategic_planner")
        assert cap is not None
        assert "strategic_planning" in cap.skills

    def test_task_router_scores_nonzero_after_scan(self, tmp_path):
        """スキルが登録された後、TaskRouter のスコアが 0 を超える。"""
        from core.intelligence.capability_registry import CapabilityRegistry
        from core.orchestration.task_router import TaskRouter
        import pathlib

        registry = CapabilityRegistry(
            platform_home=tmp_path,
            registry_file=tmp_path / "reg.json",
        )
        repo_root = pathlib.Path(__file__).parent.parent
        registry.scan_and_register_all(repo_root=repo_root)

        router = TaskRouter(capability_registry=registry)
        decision = router.route("codebase_exploration")
        assert len(decision.selected_agent_ids) > 0


# ────────────────────────────────────────────────────────────────────────────
# PreTaskOrchestrator — デフォルト factory の自動生成
# ────────────────────────────────────────────────────────────────────────────


class TestPreTaskOrchestratorDefaultFactory:
    def test_orchestrator_has_default_factory(self):
        """agent_factory を渡さなくても _agent_factory が自動生成される。"""
        from core.orchestration.pre_task_orchestrator import PreTaskOrchestrator

        orch = PreTaskOrchestrator()
        assert orch._agent_factory is not None

    def test_execute_without_factory_uses_default(self):
        """execute() に agent_factory を渡さなくてもエラーにならない。"""
        from core.orchestration.pre_task_orchestrator import PreTaskOrchestrator
        from agents.base import AgentTask, AgentResult

        orch = PreTaskOrchestrator()
        analysis = MagicMock()
        analysis.recommended_agent_ids = ["agent:strategic_planner"]

        from core.orchestration.pre_task_orchestrator import OrchestrationPattern
        analysis.recommended_pattern = OrchestrationPattern.SINGLE_AGENT

        async def _run():
            return await orch.execute(AgentTask("test", "test"), analysis)

        result = asyncio.run(_run())
        # AgentResult が返ってくる（factory が動いた証拠）
        assert result is not None
