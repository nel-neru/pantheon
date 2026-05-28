"""End-to-end tests for Sprint 6 flows."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from agents.base import AgentTask
from agents.self_code_writer import SelfCodeWriter
from agents.tool_design_agent import ToolDesignAgent
from core.execution.safe_executor import ChangeRequest, SafeChangeExecutor
from core.goals.abstract_goal_pipeline import AbstractGoalPipeline, PipelineResult
from core.goals.execution_coordinator import ExecutionCoordinator
from core.goals.goal_decomposer import EpicSpec, GoalPlan, GoalDecomposer, StorySpec, TaskSpec
from core.goals.goal_parser import GoalParser, GoalType
from core.goals.org_instantiator import OrgInstantiator
from core.hierarchy.org_designer import OrganizationDesigner
from core.intelligence.capability_gap_analyzer import CapabilityGap, CapabilityGapAnalyzer
from core.intelligence.capability_registry import CapabilityRegistry
from core.intelligence.self_extension_pipeline import SelfExtensionPipeline
from core.intelligence.self_integration_tester import SelfIntegrationTester
from core.orchestration.pre_task_orchestrator import PreTaskOrchestrator
from core.profile.developer_profile import DeveloperProfileManager
from core.state.manager import RepoStateManager


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


class TestE2EGoalFlow:
    def test_goal_parse_decompose_execute_verify(self, tmp_path):
        pipeline = AbstractGoalPipeline(
            instantiator=OrgInstantiator(org_designer=OrganizationDesigner(platform_home=tmp_path))
        )

        result = _run(pipeline.run("APIに認証付きセキュリティ改善を入れたい"))

        assert result.goal.goal_type == GoalType.SECURITY
        assert result.plan.total_tasks >= 1
        assert result.execution_progress.done_count == result.execution_progress.total
        assert result.verification.overall_achieved is True

    def test_abstract_pipeline_returns_pipeline_result(self, tmp_path):
        pipeline = AbstractGoalPipeline(
            instantiator=OrgInstantiator(org_designer=OrganizationDesigner(platform_home=tmp_path))
        )

        result = _run(pipeline.run("テストカバレッジを向上させたい"))

        assert isinstance(result, PipelineResult)
        assert result.success is True
        assert result.org_result.organization.name

    def test_pipeline_with_security_goal(self, tmp_path):
        pipeline = AbstractGoalPipeline(
            instantiator=OrgInstantiator(org_designer=OrganizationDesigner(platform_home=tmp_path))
        )

        result = _run(pipeline.run("セキュリティ脆弱性を減らしたい"))

        assert result.goal.goal_type == GoalType.SECURITY
        assert result.execution_progress.failed_count == 0

    def test_pipeline_summary_human_readable(self, tmp_path):
        pipeline = AbstractGoalPipeline(
            instantiator=OrgInstantiator(org_designer=OrganizationDesigner(platform_home=tmp_path))
        )

        result = _run(pipeline.run("パフォーマンスを改善したい"))
        summary = result.summary()

        assert "目標" in summary
        assert "達成度" in summary
        assert "Organization" in summary


class TestE2ESelfExtension:
    def test_capability_gap_detection_runs(self, tmp_path):
        detector = SimpleNamespace(
            get_repeated_patterns=lambda: [
                SimpleNamespace(
                    pattern_key="scan-cache",
                    operation_type="codebase_scan",
                    total_tokens=1200,
                )
            ]
        )
        analyzer = CapabilityGapAnalyzer(
            pattern_detector=detector,
            capability_registry=CapabilityRegistry(platform_home=tmp_path),
            platform_home=tmp_path,
        )

        gaps = analyzer.analyze()

        assert len(gaps) == 1
        assert gaps[0].suggested_name == "CodebaseExplorerAgent"

    def test_self_extension_pipeline_produces_proposal(self, tmp_path):
        gap = CapabilityGap(
            gap_id="gap:test:agent",
            pattern_key="code_review",
            description="レビュー自動化が不足している",
            suggested_type="agent",
            suggested_name="AsyncReviewAgent",
            rationale="レビュー速度を上げる",
            priority="high",
        )
        pipeline = SelfExtensionPipeline(
            gap_analyzer=None,
            design_agent=ToolDesignAgent(llm_client=None),
            code_writer=SelfCodeWriter(llm_client=None),
            integration_tester=SelfIntegrationTester(),
            state_manager=RepoStateManager(tmp_path, "TestOrg"),
        )

        result = _run(pipeline.run_for_gap(gap))
        pending = pipeline.get_pending_proposals()

        assert result.success is True
        assert result.proposal_id
        assert len(pending) == 1
        assert pending[0].category == "self_extension"

    def test_pre_task_orchestrator_analyzes_before_execute(self):
        calls = []

        class SpyOrchestrator:
            def analyze(self, task_type, description, context=None):
                calls.append((task_type, description))
                return SimpleNamespace(
                    recommended_pattern="single_agent",
                    recommended_agent_ids=["agent:test"],
                )

        plan = GoalPlan(
            plan_id="plan:test",
            goal_id="goal:test",
            goal_description="Spy orchestrator flow",
            epics=[
                EpicSpec(
                    epic_id="epic:test",
                    title="Epic",
                    description="desc",
                    stories=[
                        StorySpec(
                            story_id="story:test",
                            title="Story",
                            description="desc",
                            tasks=[
                                TaskSpec(
                                    task_id="task:test",
                                    title="Analyze before execute",
                                    description="Run orchestrator first",
                                    required_skills=["deep_research"],
                                    agent_type="code_review",
                                )
                            ],
                        )
                    ],
                )
            ],
        )

        progress = _run(ExecutionCoordinator(pre_task_orchestrator=SpyOrchestrator()).execute(plan))

        assert calls == [("code_review", "Run orchestrator first")]
        assert "パターン" in progress.task_progresses["task:test"].result_summary


class TestE2ECoevolution:
    def test_developer_profile_records_approval(self, tmp_path):
        manager = DeveloperProfileManager(platform_home=tmp_path)
        manager.record_approval("security", approved=True)
        manager.record_approval("security", approved=True)
        manager.record_approval("security", approved=True)

        profile = manager.get_profile()

        assert profile.approval_patterns["security"].approved_count == 3
        assert "security" in profile.preferred_categories

    def test_org_designer_creates_org_from_purpose(self, tmp_path):
        designer = OrganizationDesigner(platform_home=tmp_path)
        spec = designer.design("Improve security posture and knowledge sharing", org_name="Ops Org")
        organization = designer.instantiate(spec)

        assert organization.name == "Ops Org"
        assert len(organization.divisions) >= 2
        assert len(organization.get_all_agents()) >= 2

    def test_safe_executor_backup_restore(self, tmp_path, monkeypatch):
        target = tmp_path / "service.py"
        target.write_text("before\n", encoding="utf-8")
        executor = SafeChangeExecutor(project_root=tmp_path)
        backup = executor.create_backup(str(target))

        monkeypatch.setattr(
            executor,
            "_run_tests",
            lambda: (True, "1 passed", {"passed": 1, "failed": 0, "errors": 0}),
        )

        result = executor.apply_change(
            ChangeRequest(
                file_path=str(target),
                new_content="after\n",
                description="update file",
            )
        )

        restored = executor.rollback(backup)

        assert result.success is True
        assert restored is True
        assert target.read_text(encoding="utf-8") == "before\n"
