"""
tests/test_yaml_loaders.py

SkillLoader / AgentLoader / YAML定義からのエージェント生成を検証するテスト。

- skills/*.yaml が正しく読み込まれること
- agents/definitions/*.yaml が正しく読み込まれること
- YAMLからのエージェントがスキルプロンプトを正しく生成すること
- YAMLファイルを追加するだけで新エージェントが使えること
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


# ────────────────────────────────────────────────────────────────────────────
# SkillLoader
# ────────────────────────────────────────────────────────────────────────────


class TestSkillLoader:
    def test_loads_all_skills(self):
        from core.loaders.skill_loader import SkillLoader

        loader = SkillLoader()
        skills = loader.all()
        expected = len(list((Path(__file__).resolve().parent.parent / "skills").glob("*.yaml")))
        assert len(skills) == expected

    def test_strategic_planning_loaded(self):
        from core.loaders.skill_loader import SkillLoader

        loader = SkillLoader()
        skill = loader.get("strategic_planning")
        assert skill is not None
        assert skill.id == "strategic_planning"
        assert skill.persona  # ペルソナが設定されている

    def test_quality_guardian_loaded(self):
        from core.loaders.skill_loader import SkillLoader

        loader = SkillLoader()
        skill = loader.get("quality_guardian")
        assert skill is not None
        assert skill.id == "quality_guardian"
        assert "品質管理者" in skill.persona

    def test_to_prompt_addon_contains_persona_and_focus(self):
        from core.loaders.skill_loader import SkillLoader

        loader = SkillLoader()
        skill = loader.get("codebase_exploration")
        assert skill is not None
        prompt = skill.to_prompt_addon()
        assert len(prompt) > 50
        # ペルソナと注力点が含まれること
        assert "コードベース" in prompt or "exploration" in prompt.lower()

    def test_all_skills_have_required_fields(self):
        from core.loaders.skill_loader import SkillLoader

        loader = SkillLoader()
        for skill in loader.all():
            assert skill.id, f"Skill {skill!r} has no id"
            assert skill.name, f"Skill {skill.id!r} has no name"
            assert skill.persona, f"Skill {skill.id!r} has no persona"

    def test_reload_returns_count(self):
        from core.loaders.skill_loader import SkillLoader

        loader = SkillLoader()
        count = loader.reload()
        expected = len(list((Path(__file__).resolve().parent.parent / "skills").glob("*.yaml")))
        assert count == expected

    def test_unknown_skill_returns_none(self):
        from core.loaders.skill_loader import SkillLoader

        loader = SkillLoader()
        assert loader.get("nonexistent_skill_xyz") is None

    def test_custom_skills_dir(self, tmp_path):
        """存在しないディレクトリはエラーにならない。"""
        from core.loaders.skill_loader import SkillLoader

        loader = SkillLoader(skills_dir=tmp_path / "no_such_dir")
        assert loader.all() == []

    def test_yaml_file_adds_skill(self, tmp_path):
        """tmp_path に YAML を置くと新スキルとして認識される。"""
        from core.loaders.skill_loader import SkillLoader
        import yaml

        skill_yaml = tmp_path / "custom_skill.yaml"
        skill_yaml.write_text(
            yaml.dump({
                "id": "custom_skill",
                "name": "Custom Skill",
                "persona": "あなたはカスタムスキルの専門家です。",
                "focus": "カスタム分析を行います。",
                "output_hint": "カスタム形式で返してください。",
            }),
            encoding="utf-8",
        )
        loader = SkillLoader(skills_dir=tmp_path)
        skill = loader.get("custom_skill")
        assert skill is not None
        assert skill.name == "Custom Skill"


# ────────────────────────────────────────────────────────────────────────────
# AgentLoader
# ────────────────────────────────────────────────────────────────────────────


class TestAgentLoader:
    def test_loads_all_yaml_agents(self):
        from core.loaders.agent_loader import AgentLoader

        loader = AgentLoader()
        agents = loader.all()
        expected = len(list((Path(__file__).resolve().parent.parent / "agents" / "definitions").glob("*.yaml")))
        assert len(agents) == expected

    def test_strategic_planner_loaded(self):
        from core.loaders.agent_loader import AgentLoader

        loader = AgentLoader()
        defn = loader.get("agent:strategic_planner")
        assert defn is not None
        assert defn.name == "StrategicPlanner"
        assert "strategic_planning" in defn.skills
        assert "org_design" in defn.skills

    def test_quality_guardian_loaded(self):
        from core.loaders.agent_loader import AgentLoader

        loader = AgentLoader()
        defn = loader.get("agent:quality_guardian")
        assert defn is not None
        assert defn.name == "QualityGuardian"
        assert "quality_guardian" in defn.skills
        assert "code_review" in defn.skills

    def test_agent_has_behavior(self):
        from core.loaders.agent_loader import AgentLoader

        loader = AgentLoader()
        for defn in loader.all():
            assert defn.behavior.strip(), f"Agent {defn.name!r} has no behavior"

    def test_agent_has_response_format(self):
        from core.loaders.agent_loader import AgentLoader

        loader = AgentLoader()
        defn = loader.get("agent:security_auditor")
        assert defn is not None
        assert defn.response_format.get("type") == "json"

    def test_capability_id_format(self):
        """全エージェントの capability_id が 'agent:' プレフィックスを持つ。"""
        from core.loaders.agent_loader import AgentLoader

        loader = AgentLoader()
        for defn in loader.all():
            assert defn.capability_id.startswith("agent:"), \
                f"{defn.name!r} has invalid capability_id: {defn.capability_id!r}"

    def test_new_yaml_file_creates_new_agent(self, tmp_path):
        """YAML ファイルを追加するだけで新エージェントが認識される（Pythonコード不要）。"""
        from core.loaders.agent_loader import AgentLoader
        import yaml

        # 新エージェント定義を tmp_path に作成
        (tmp_path / "my_new_agent.yaml").write_text(
            yaml.dump({
                "name": "MyNewAgent",
                "description": "テスト用カスタムエージェント",
                "skills": ["strategic_planning", "deep_research"],
                "tools": ["read_file"],
                "behavior": "テスト専用の振る舞いです。",
                "response_format": {"type": "json", "fields": ["result"]},
            }),
            encoding="utf-8",
        )
        loader = AgentLoader(definitions_dir=tmp_path)
        defn = loader.get("agent:my_new_agent")
        assert defn is not None
        assert defn.name == "MyNewAgent"
        assert "strategic_planning" in defn.skills


# ────────────────────────────────────────────────────────────────────────────
# AgentDefinition.build_system_prompt
# ────────────────────────────────────────────────────────────────────────────


class TestAgentDefinitionBuildSystemPrompt:
    def test_prompt_contains_behavior(self):
        from core.loaders.agent_loader import AgentLoader

        loader = AgentLoader()
        defn = loader.get("agent:strategic_planner")
        prompt = defn.build_system_prompt()
        assert defn.behavior.strip()[:20] in prompt or "ビジョン" in prompt

    def test_prompt_contains_skill_persona_when_loader_provided(self):
        from core.loaders.agent_loader import AgentLoader
        from core.loaders.skill_loader import SkillLoader

        agent_loader = AgentLoader()
        skill_loader = SkillLoader()
        defn = agent_loader.get("agent:strategic_planner")
        prompt = defn.build_system_prompt(skill_loader=skill_loader)
        # strategic_planning のペルソナが含まれること
        assert "ビジョナリー" in prompt or "戦略" in prompt

    def test_prompt_contains_response_format_hint(self):
        from core.loaders.agent_loader import AgentLoader

        loader = AgentLoader()
        defn = loader.get("agent:security_auditor")
        prompt = defn.build_system_prompt()
        assert "JSON" in prompt or "json" in prompt


# ────────────────────────────────────────────────────────────────────────────
# AgentFactory — YAML優先動作
# ────────────────────────────────────────────────────────────────────────────


class TestAgentFactoryYamlPriority:
    def test_yaml_agent_is_returned_for_strategic_planner(self):
        """agents/definitions/strategic_planner.yaml からエージェントが生成される。"""
        from agents.agent_factory import AgentFactory
        from agents.generic_skill_agent import GenericSkillAgent

        factory = AgentFactory()
        agent = factory.create("agent:strategic_planner")
        assert agent is not None
        assert isinstance(agent, GenericSkillAgent)  # _YamlAgent は GenericSkillAgent のサブクラス

    def test_yaml_agent_prompt_includes_behavior(self):
        """YAMLのbehaviorがシステムプロンプトに反映される。"""
        from agents.agent_factory import AgentFactory

        factory = AgentFactory()
        agent = factory.create("agent:strategic_planner")
        assert agent is not None
        prompt = agent.apply_skills_to_prompt("BASE")
        # YAML behavior の内容が含まれる
        assert "Conway" in prompt or "ビジョン" in prompt or "全体" in prompt

    def test_yaml_agent_runs(self):
        """YAMLから生成されたエージェントが実行できる。"""
        from agents.agent_factory import AgentFactory
        from agents.base import AgentTask

        factory = AgentFactory()
        agent = factory.create("agent:security_auditor")
        assert agent is not None
        task = AgentTask("security_audit", "セキュリティ監査を実施せよ")
        result = asyncio.run(agent.run(task))
        assert result.success

    def test_all_yaml_agents_can_be_instantiated(self):
        """YAML定義の全エージェントがインスタンス化できる。"""
        from agents.agent_factory import AgentFactory
        from core.loaders.agent_loader import AgentLoader

        factory = AgentFactory()
        loader = AgentLoader()
        for defn in loader.all():
            agent = factory.create(defn.capability_id)
            assert agent is not None, f"Failed to create agent for {defn.capability_id!r}"

    def test_skill_loader_used_in_prompt(self):
        """skills/*.yaml のペルソナがエージェントプロンプトに反映される。"""
        from agents.agent_factory import AgentFactory

        factory = AgentFactory()
        agent = factory.create("agent:knowledge_curator")
        assert agent is not None
        prompt = agent.apply_skills_to_prompt("BASE")
        # knowledge_curation の YAML ペルソナ（「6ヶ月後の自分」）が入っているはず
        assert len(prompt) > len("BASE") + 50  # 何かが注入されている
