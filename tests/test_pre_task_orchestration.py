"""
Tests for Pre-Task Orchestration Layer (Theme N):
  - PreTaskOrchestrator
  - TaskRouter
  - DynamicAgentSpawner
  - OrchestrationPatternStore
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from agents.base import AgentResult, AgentTask
from core.orchestration.dynamic_agent_spawner import DynamicAgentSpawner, SpawnRequest
from core.orchestration.orchestration_pattern_store import (
    OrchestrationPatternStore,
    PatternRecord,
)
from core.orchestration.pre_task_orchestrator import (
    OrchestrationPattern,
    PreTaskOrchestrator,
    TaskAnalysis,
)
from core.orchestration.task_router import TaskRouter

# ═══════════════════════════════════════════════════════════════
# TaskRouter テスト
# ═══════════════════════════════════════════════════════════════


class TestTaskRouter:
    def _make_registry(self, agent_skills: dict[str, list[str]]):
        """指定スキルセットを持つエージェントが登録されたモックレジストリを返す。"""
        registry = MagicMock()
        entries = []
        for name, skills in agent_skills.items():
            entry = MagicMock()
            entry.id = f"agent:{name}"
            entry.name = name
            entry.skills = skills
            entry.usage_count = 0
            entries.append(entry)
        registry.list_agents.return_value = entries
        return registry

    def test_routes_to_agent_with_matching_skill(self):
        registry = self._make_registry(
            {
                "Explorer": ["codebase_exploration", "deep_research"],
                "Planner": ["strategic_planning", "org_design"],
            }
        )
        router = TaskRouter(capability_registry=registry)
        decision = router.route("codebase_exploration")
        assert "agent:Explorer" in decision.selected_agent_ids

    def test_returns_empty_when_no_registry(self):
        router = TaskRouter(capability_registry=None)
        decision = router.route("code_review")
        assert decision.selected_agent_ids == []
        assert decision.fallback_used

    def test_fallback_flag_when_low_score(self):
        registry = self._make_registry(
            {
                "Planner": ["strategic_planning", "org_design"],
            }
        )
        router = TaskRouter(capability_registry=registry)
        # security_audit requires tool_integration + deep_research; Planner doesn't have those
        decision = router.route("security_audit")
        assert decision.fallback_used

    def test_max_agents_limit(self):
        registry = self._make_registry(
            {
                "A": ["codebase_exploration", "deep_research"],
                "B": ["codebase_exploration", "performance_analysis"],
                "C": ["codebase_exploration", "knowledge_curation"],
            }
        )
        router = TaskRouter(capability_registry=registry)
        decision = router.route("code_review", max_agents=2)
        assert len(decision.selected_agent_ids) <= 2

    def test_get_task_type_capabilities_returns_dict(self):
        router = TaskRouter()
        caps = router.get_task_type_capabilities()
        assert isinstance(caps, dict)
        assert "code_review" in caps
        assert "codebase_exploration" in caps["code_review"]


# ═══════════════════════════════════════════════════════════════
# DynamicAgentSpawner テスト
# ═══════════════════════════════════════════════════════════════


class TestDynamicAgentSpawner:
    def test_spawns_agent_with_resolved_skills(self):
        spawner = DynamicAgentSpawner()
        req = SpawnRequest(
            required_skills=["codebase_exploration", "deep_research"],
            purpose="テスト用エージェント",
        )
        result = spawner.spawn(req)
        assert result.success
        assert result.agent is not None
        assert len(result.agent.skills) >= 2

    def test_spawned_agent_added_to_history(self):
        spawner = DynamicAgentSpawner()
        req = SpawnRequest(
            required_skills=["strategic_planning", "org_design"],
            purpose="テスト",
        )
        spawner.spawn(req)
        assert len(spawner.get_spawned_agents()) == 1

    def test_fallback_when_skill_not_enum(self):
        """AgentSkill enum に存在しないスキル名でも動作すること。"""
        spawner = DynamicAgentSpawner()
        req = SpawnRequest(
            required_skills=["security", "research"],  # エイリアス
            purpose="テスト",
        )
        result = spawner.spawn(req)
        assert result.success
        assert result.agent is not None

    def test_generates_name_from_primary_skill(self):
        spawner = DynamicAgentSpawner()
        req = SpawnRequest(
            required_skills=["performance_analysis", "deep_research"],
            purpose="テスト",
        )
        result = spawner.spawn(req)
        assert "Performance" in result.agent.name or "Specialist" in result.agent.name

    def test_suggested_name_is_used(self):
        spawner = DynamicAgentSpawner()
        req = SpawnRequest(
            required_skills=["codebase_exploration", "deep_research"],
            purpose="テスト",
            suggested_name="MyCustomAgent",
        )
        result = spawner.spawn(req)
        assert result.agent.name == "MyCustomAgent"

    def test_single_resolved_skill_equal_to_fallback_still_gets_two_skills(self):
        """解決結果が1個かつ既定フォールバック(deep_research)と一致しても、
        重複を避けて別スキルを足し min2 を満たす（SpecialistAgent.skills の min_length=2 を保証）。"""
        spawner = DynamicAgentSpawner()
        req = SpawnRequest(required_skills=["deep_research"], purpose="テスト")
        result = spawner.spawn(req)
        assert result.success
        assert result.agent is not None
        skill_values = [s.value for s in result.agent.skills]
        assert len(skill_values) >= 2
        assert len(set(skill_values)) == len(skill_values)  # 重複なし
        assert "deep_research" in skill_values

    def test_all_unresolvable_skills_still_produce_valid_agent(self):
        """全スキル名が AgentSkill にもエイリアスにも解決できなくても、
        フォールバックで2スキル以上の有効なエージェントを作る。"""
        spawner = DynamicAgentSpawner()
        req = SpawnRequest(required_skills=["xyzzy", "foobar"], purpose="テスト")
        result = spawner.spawn(req)
        assert result.success
        assert result.agent is not None
        assert len(result.agent.skills) >= 2


# ═══════════════════════════════════════════════════════════════
# OrchestrationPatternStore テスト
# ═══════════════════════════════════════════════════════════════


class TestOrchestrationPatternStore:
    def test_record_and_get_stats(self, tmp_path):
        store = OrchestrationPatternStore(platform_home=tmp_path)
        store.record(
            PatternRecord(
                task_type="code_review",
                pattern=OrchestrationPattern.REVIEW_LOOP,
                agent_ids=["agent:Explorer"],
                success=True,
            )
        )
        stats = store.get_stats_for_task("code_review")
        assert len(stats) == 1
        assert stats[0].total_runs == 1
        assert stats[0].success_rate == 1.0

    def test_get_best_pattern_requires_3_records(self, tmp_path):
        store = OrchestrationPatternStore(platform_home=tmp_path)
        # 2件 → まだ推奨なし
        for _ in range(2):
            store.record(
                PatternRecord(
                    task_type="code_review",
                    pattern=OrchestrationPattern.REVIEW_LOOP,
                    agent_ids=[],
                    success=True,
                )
            )
        assert store.get_best_pattern("code_review") is None

        # 3件 → 推奨あり
        store.record(
            PatternRecord(
                task_type="code_review",
                pattern=OrchestrationPattern.REVIEW_LOOP,
                agent_ids=[],
                success=True,
            )
        )
        assert store.get_best_pattern("code_review") == OrchestrationPattern.REVIEW_LOOP

    def test_best_pattern_is_highest_success_rate(self, tmp_path):
        store = OrchestrationPatternStore(platform_home=tmp_path)
        # single_agent: 2成功1失敗
        for s in [True, True, False]:
            store.record(
                PatternRecord(
                    task_type="code_review",
                    pattern=OrchestrationPattern.SINGLE_AGENT,
                    agent_ids=[],
                    success=s,
                )
            )
        # review_loop: 3成功
        for _ in range(3):
            store.record(
                PatternRecord(
                    task_type="code_review",
                    pattern=OrchestrationPattern.REVIEW_LOOP,
                    agent_ids=[],
                    success=True,
                )
            )
        best = store.get_best_pattern("code_review")
        assert best == OrchestrationPattern.REVIEW_LOOP

    def test_persistence(self, tmp_path):
        store1 = OrchestrationPatternStore(platform_home=tmp_path)
        for _ in range(3):
            store1.record(
                PatternRecord(
                    task_type="meta_improvement",
                    pattern=OrchestrationPattern.HIERARCHICAL,
                    agent_ids=[],
                    success=True,
                )
            )
        # 別インスタンスでロード
        store2 = OrchestrationPatternStore(platform_home=tmp_path)
        assert store2.get_best_pattern("meta_improvement") == OrchestrationPattern.HIERARCHICAL


# ═══════════════════════════════════════════════════════════════
# PreTaskOrchestrator テスト
# ═══════════════════════════════════════════════════════════════


class TestPreTaskOrchestrator:
    def test_analyze_returns_task_analysis(self):
        orchestrator = PreTaskOrchestrator()
        analysis = orchestrator.analyze("code_review", "セキュリティ問題の調査")
        assert isinstance(analysis, TaskAnalysis)
        assert analysis.task_type == "code_review"
        assert analysis.recommended_pattern == OrchestrationPattern.REVIEW_LOOP

    def test_analyze_uses_default_profile_for_unknown_task(self):
        orchestrator = PreTaskOrchestrator()
        analysis = orchestrator.analyze("unknown_task_xyz", "テスト")
        assert analysis.recommended_pattern == OrchestrationPattern.SINGLE_AGENT

    def test_analyze_respects_pattern_store(self, tmp_path):
        store = OrchestrationPatternStore(platform_home=tmp_path)
        # 学習データ: hierarchical が成功
        for _ in range(3):
            store.record(
                PatternRecord(
                    task_type="code_review",
                    pattern=OrchestrationPattern.HIERARCHICAL,
                    agent_ids=[],
                    success=True,
                )
            )
        orchestrator = PreTaskOrchestrator(pattern_store=store)
        analysis = orchestrator.analyze("code_review", "テスト")
        # パターンストアの学習結果が使われる
        assert analysis.recommended_pattern == OrchestrationPattern.HIERARCHICAL

    def test_execute_single_agent(self):
        mock_result = AgentResult(success=True, output={"test": 1})

        async def fake_agent_run(task):
            return mock_result

        mock_agent = MagicMock()
        mock_agent.run = fake_agent_run

        def factory(agent_id):
            return mock_agent

        orchestrator = PreTaskOrchestrator()
        analysis = TaskAnalysis(
            task_type="code_review",
            description="テスト",
            recommended_pattern=OrchestrationPattern.SINGLE_AGENT,
            recommended_agent_ids=["agent:test"],
        )
        task = AgentTask(task_type="code_review", description="テスト")
        result = asyncio.run(orchestrator.execute(task, analysis, agent_factory=factory))
        assert result.success

    def test_execute_single_returns_error_when_no_agent_selected(self):
        orchestrator = PreTaskOrchestrator()
        analysis = TaskAnalysis(
            task_type="code_review",
            description="テスト",
            recommended_pattern=OrchestrationPattern.SINGLE_AGENT,
            recommended_agent_ids=[],
        )
        task = AgentTask(task_type="code_review", description="テスト")

        result = asyncio.run(orchestrator.execute(task, analysis, agent_factory=lambda _: None))

        assert result.success is False
        assert result.error == "No agent selected"

    def test_execute_spawns_runs_and_registers_when_no_agent_fits(self, tmp_path):
        """spawn_new_agent のとき DynamicAgentSpawner が能力を registry に登録し、
        create_for_skills で生成した runnable エージェントを実行する（従来の
        'spawn_spec を作るだけで実行しない' dead-code 経路を置き換える）。"""
        from core.intelligence.capability_registry import CapabilityRegistry

        mock_result = AgentResult(success=True, output="spawned-ran")

        async def fake_run(task):
            return mock_result

        mock_agent = MagicMock()
        mock_agent.run = fake_run

        class FakeFactory:
            def __init__(self):
                self.spawned_skills = None

            def create(self, agent_id):
                return None

            def create_for_skills(self, skills, name=None):
                self.spawned_skills = list(skills)
                return mock_agent

        registry = CapabilityRegistry(platform_home=tmp_path)
        factory = FakeFactory()
        orchestrator = PreTaskOrchestrator(capability_registry=registry, agent_factory=factory)
        analysis = TaskAnalysis(
            task_type="code_review",
            description="テスト",
            recommended_pattern=OrchestrationPattern.SINGLE_AGENT,
            recommended_agent_ids=[],
            spawn_new_agent=True,
            spawn_spec={"skills": ["strategic_planning", "deep_research"], "reason": "no fit"},
        )
        task = AgentTask(task_type="code_review", description="テスト")
        result = asyncio.run(orchestrator.execute(task, analysis, record=False))

        # runnable エージェントが生成・実行された（従来は "No agent selected" 失敗）
        assert result.success
        assert result.output == "spawned-ran"
        assert factory.spawned_skills is not None and len(factory.spawned_skills) >= 2
        # DynamicAgentSpawner が実際に呼ばれ、能力を registry に登録した（自己拡張）
        dynamic = [e for e in registry.list_agents() if e.id.startswith("agent:dynamic:")]
        assert len(dynamic) == 1

    def test_execute_spawn_without_factory_returns_informative_error(self):
        """spawn が推奨されても create_for_skills 可能な factory が無い場合、
        クラッシュせず説明的なエラーを返す（graceful degradation）。"""
        orchestrator = PreTaskOrchestrator()
        orchestrator._agent_factory = None  # factory 不在を強制
        analysis = TaskAnalysis(
            task_type="code_review",
            description="テスト",
            recommended_pattern=OrchestrationPattern.SINGLE_AGENT,
            recommended_agent_ids=[],
            spawn_new_agent=True,
            spawn_spec={"skills": ["deep_research", "codebase_exploration"], "reason": "no fit"},
        )
        task = AgentTask(task_type="code_review", description="テスト")
        # execute が analysis-only に早期 return しないよう callable を渡す（spawn 経路は self._agent_factory を使う）
        result = asyncio.run(
            orchestrator.execute(task, analysis, agent_factory=lambda _: None, record=False)
        )

        assert result.success is False
        assert "factory" in result.error.lower()

    def test_execute_parallel_returns_error_when_all_agents_fail(self):
        class FailingAgent:
            async def run(self, task):
                return AgentResult(success=False, error="boom")

        orchestrator = PreTaskOrchestrator()
        analysis = TaskAnalysis(
            task_type="code_review",
            description="テスト",
            recommended_pattern=OrchestrationPattern.PARALLEL_THEN_MERGE,
            recommended_agent_ids=["agent:a", "agent:b"],
        )
        task = AgentTask(task_type="code_review", description="テスト")

        result = asyncio.run(
            orchestrator.execute(task, analysis, agent_factory=lambda _: FailingAgent())
        )

        assert result.success is False
        assert result.error == "All parallel agents failed"

    def test_execute_without_factory_uses_default_factory(self):
        """agent_factory=None を明示的に渡した場合、
        デフォルト AgentFactory を使うため analysis がそのまま返ることはなくなった。
        代わりに AgentResult が返ること（エージェント選択失敗も含む）を確認する。"""
        orchestrator = PreTaskOrchestrator()
        analysis = orchestrator.analyze("codebase_exploration", "テスト")
        task = AgentTask(task_type="codebase_exploration", description="テスト")
        result = asyncio.run(orchestrator.execute(task, analysis, agent_factory=None))
        # デフォルト factory が使われるため AgentResult が返る（TaskAnalysis ではない）
        from agents.base import AgentResult

        assert isinstance(result, AgentResult)

    def test_plan_and_execute_convenience(self):
        orchestrator = PreTaskOrchestrator()
        task = AgentTask(task_type="code_review", description="テスト")
        result = asyncio.run(orchestrator.plan_and_execute("code_review", task))
        assert result is not None  # analysis が返る

    def test_execution_is_recorded_in_log(self, tmp_path):
        store = OrchestrationPatternStore(platform_home=tmp_path)
        orchestrator = PreTaskOrchestrator(pattern_store=store)
        analysis = TaskAnalysis(
            task_type="code_review",
            description="テスト",
            recommended_pattern=OrchestrationPattern.SINGLE_AGENT,
            recommended_agent_ids=[],
        )
        task = AgentTask(task_type="code_review", description="テスト")
        mock_result = AgentResult(success=True)
        orchestrator._record_execution(task, analysis, mock_result)
        assert len(orchestrator.get_execution_log()) == 1

    def test_pattern_summary(self):
        orchestrator = PreTaskOrchestrator()
        analysis = TaskAnalysis(
            task_type="code_review",
            description="テスト",
            recommended_pattern=OrchestrationPattern.REVIEW_LOOP,
            recommended_agent_ids=[],
        )
        task = AgentTask(task_type="code_review", description="テスト")
        orchestrator._record_execution(task, analysis, AgentResult(success=True))
        orchestrator._record_execution(task, analysis, AgentResult(success=False))
        summary = orchestrator.get_pattern_summary()
        assert summary["total_executions"] == 2
        assert OrchestrationPattern.REVIEW_LOOP in summary["pattern_counts"]
