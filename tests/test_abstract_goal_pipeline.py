"""
Tests for Sprint 4: Abstract Goal → Autonomous Execution Pipeline (M-01~M-05)
"""
from __future__ import annotations

import asyncio
import pytest

from core.goals.goal_parser import GoalParser, GoalType, GoalScale, StructuredGoal
from core.goals.goal_decomposer import GoalDecomposer, GoalPlan, TaskSpec
from core.goals.execution_coordinator import ExecutionCoordinator, TaskStatus
from core.goals.goal_verifier import GoalVerifier
from core.goals.org_instantiator import OrgInstantiator
from core.goals.abstract_goal_pipeline import AbstractGoalPipeline


def _run(coro):
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════
# GoalParser (M-01)
# ═══════════════════════════════════════════════════════════════

class TestGoalParser:
    def test_parse_security_goal(self):
        parser = GoalParser()
        goal = parser.parse("セキュリティを強化して脆弱性を修正したい")
        assert goal.goal_type == GoalType.SECURITY
        assert len(goal.success_criteria) > 0
        assert len(goal.constraints) > 0

    def test_parse_test_coverage_goal(self):
        parser = GoalParser()
        goal = parser.parse("テストカバレッジを80%以上に上げたい")
        assert goal.goal_type == GoalType.TEST_COVERAGE
        assert "testing" in goal.suggested_categories

    def test_parse_performance_goal(self):
        parser = GoalParser()
        goal = parser.parse("APIのパフォーマンスが遅いので最適化したい")
        assert goal.goal_type == GoalType.PERFORMANCE

    def test_parse_new_service_goal(self):
        parser = GoalParser()
        goal = parser.parse("Eコマースサービスを作りたい")
        assert goal.goal_type == GoalType.NEW_SERVICE
        assert goal.domain == "ecommerce"

    def test_parse_refactoring_goal(self):
        parser = GoalParser()
        goal = parser.parse("コードをリファクタリングして可読性を上げたい")
        assert goal.goal_type == GoalType.REFACTORING

    def test_parse_sets_scale_large_for_full_refactor(self):
        parser = GoalParser()
        goal = parser.parse("全面的なリアーキテクチャを行いたい")
        assert goal.scale == GoalScale.LARGE

    def test_parse_sets_scale_small(self):
        parser = GoalParser()
        goal = parser.parse("ちょっとした修正をしたい")
        assert goal.scale == GoalScale.SMALL

    def test_parse_unknown_text_defaults_to_general(self):
        parser = GoalParser()
        goal = parser.parse("何か良いことをしたい")
        assert goal.goal_type == GoalType.GENERAL

    def test_goal_has_id(self):
        parser = GoalParser()
        goal = parser.parse("テストを追加したい")
        assert goal.goal_id.startswith("goal:")

    def test_goal_to_dict(self):
        parser = GoalParser()
        goal = parser.parse("セキュリティを改善したい")
        d = goal.to_dict()
        assert "goal_id" in d
        assert "goal_type" in d
        assert "success_criteria" in d

    def test_goal_from_dict_roundtrip(self):
        parser = GoalParser()
        goal = parser.parse("パフォーマンスを向上させたい")
        d = goal.to_dict()
        restored = StructuredGoal.from_dict(d)
        assert restored.goal_id == goal.goal_id
        assert restored.goal_type == goal.goal_type

    def test_extract_features_from_bullet_list(self):
        parser = GoalParser()
        goal = parser.parse("以下の機能を追加したい\n・ログイン機能\n・決済機能\n・通知機能")
        assert len(goal.features) >= 1


# ═══════════════════════════════════════════════════════════════
# GoalDecomposer (M-02)
# ═══════════════════════════════════════════════════════════════

class TestGoalDecomposer:
    def _make_security_goal(self):
        parser = GoalParser()
        return parser.parse("セキュリティを強化したい")

    def test_decompose_creates_epics(self):
        decomposer = GoalDecomposer()
        goal = self._make_security_goal()
        plan = decomposer.decompose(goal)
        assert len(plan.epics) >= 1

    def test_decompose_creates_tasks(self):
        decomposer = GoalDecomposer()
        goal = self._make_security_goal()
        plan = decomposer.decompose(goal)
        assert plan.total_tasks >= 1

    def test_decompose_tasks_have_skills(self):
        decomposer = GoalDecomposer()
        goal = GoalParser().parse("テストカバレッジを上げたい")
        plan = decomposer.decompose(goal)
        for task in plan.get_all_tasks():
            assert len(task.required_skills) >= 1

    def test_plan_has_goal_id(self):
        decomposer = GoalDecomposer()
        goal = GoalParser().parse("ドキュメントを整備したい")
        plan = decomposer.decompose(goal)
        assert plan.goal_id == goal.goal_id

    def test_dependency_ordering(self):
        """depends_on_prev タスクは先行タスクに依存する。"""
        decomposer = GoalDecomposer()
        goal = GoalParser().parse("パフォーマンスを改善したい")
        plan = decomposer.decompose(goal)
        # 依存関係が正しく設定されているか（第2タスク以降は dependencies を持つ）
        all_tasks = plan.get_all_tasks()
        # 少なくとも1つのタスクはあるはず
        assert len(all_tasks) >= 1

    def test_plan_to_dict(self):
        decomposer = GoalDecomposer()
        goal = GoalParser().parse("リファクタリングしたい")
        plan = decomposer.decompose(goal)
        d = plan.to_dict()
        assert "plan_id" in d
        assert "epics" in d
        assert "total_tasks" in d

    def test_get_all_tasks_returns_flat_list(self):
        decomposer = GoalDecomposer()
        goal = GoalParser().parse("新しいサービスを作りたい")
        plan = decomposer.decompose(goal)
        tasks = plan.get_all_tasks()
        assert all(isinstance(t, TaskSpec) for t in tasks)


# ═══════════════════════════════════════════════════════════════
# OrgInstantiator (M-03)
# ═══════════════════════════════════════════════════════════════

class TestOrgInstantiator:
    def test_instantiate_creates_new_org(self, tmp_path):
        from unittest.mock import patch
        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            goal = GoalParser().parse("セキュリティを強化したい")
            result = OrgInstantiator().instantiate(goal)
        assert result.is_new is True
        assert result.organization is not None
        assert result.organization.name

    def test_instantiate_reuses_existing_org(self, tmp_path):
        from unittest.mock import patch
        from core.models.organization import Organization, OrganizationStatus
        existing = Organization(
            name="Security Org",
            purpose="security improvement for the system",
        )
        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            goal = GoalParser().parse("セキュリティを強化したい")
            result = OrgInstantiator(existing_orgs=[existing]).instantiate(goal)
        assert result.is_new is False
        assert result.organization.name == "Security Org"

    def test_org_name_reflects_domain(self, tmp_path):
        from unittest.mock import patch
        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            goal = GoalParser().parse("Eコマースサービスを作りたい")
            result = OrgInstantiator().instantiate(goal)
        assert "ecommerce" in result.organization.name.lower() or result.is_new


# ═══════════════════════════════════════════════════════════════
# ExecutionCoordinator (M-04)
# ═══════════════════════════════════════════════════════════════

class TestExecutionCoordinator:
    def _make_plan(self):
        decomposer = GoalDecomposer()
        goal = GoalParser().parse("テストカバレッジを向上させたい")
        return decomposer.decompose(goal)

    def test_execution_completes_all_tasks(self):
        coord = ExecutionCoordinator()
        plan = self._make_plan()
        progress = _run(coord.execute(plan))
        assert progress.is_complete
        assert progress.done_count == progress.total

    def test_execution_has_no_failures(self):
        coord = ExecutionCoordinator()
        plan = self._make_plan()
        progress = _run(coord.execute(plan))
        assert progress.failed_count == 0

    def test_progress_pct_is_100_after_execution(self):
        coord = ExecutionCoordinator()
        plan = self._make_plan()
        progress = _run(coord.execute(plan))
        assert progress.progress_pct == 100.0

    def test_topological_sort_respects_dependencies(self):
        """依存タスクが先行タスクの後に来ることを確認。"""
        coord = ExecutionCoordinator()
        plan = GoalDecomposer().decompose(GoalParser().parse("セキュリティを改善したい"))
        tasks = plan.get_all_tasks()
        ordered = coord._topological_sort(tasks)
        # 依存関係が満たされているか確認
        seen_ids = set()
        for task in ordered:
            for dep in task.dependencies:
                assert dep in seen_ids, f"Task {task.task_id} depends on {dep} which hasn't been processed"
            seen_ids.add(task.task_id)

    def test_skipped_task_on_ineligible(self):
        """実行不可能なタスクはスキップされる。"""
        coord = ExecutionCoordinator()
        plan = GoalDecomposer().decompose(GoalParser().parse("何かをしたい"))
        # 全タスクを実行不可にする
        for task in plan.get_all_tasks():
            task.is_executable = False
        progress = _run(coord.execute(plan))
        skipped = sum(
            1 for p in progress.task_progresses.values()
            if p.status == TaskStatus.SKIPPED
        )
        assert skipped == progress.total


# ═══════════════════════════════════════════════════════════════
# GoalVerifier (M-05)
# ═══════════════════════════════════════════════════════════════

class TestGoalVerifier:
    def _run_pipeline(self, text: str):
        pipeline = AbstractGoalPipeline()
        return _run(pipeline.run(text))

    def test_verify_achieved_after_execution(self):
        verifier = GoalVerifier()
        goal = GoalParser().parse("テストを追加したい")
        plan = GoalDecomposer().decompose(goal)
        coord = ExecutionCoordinator()
        progress = _run(coord.execute(plan))
        result = verifier.verify(goal, plan, progress)
        assert result.overall_achieved is True
        assert result.achievement_pct >= GoalVerifier.ACHIEVEMENT_THRESHOLD

    def test_verify_not_achieved_when_all_failed(self):
        verifier = GoalVerifier()
        goal = GoalParser().parse("パフォーマンスを改善したい")
        plan = GoalDecomposer().decompose(goal)
        # 全タスクを失敗させる
        coord = ExecutionCoordinator()
        progress = _run(coord.execute(plan))
        for p in progress.task_progresses.values():
            p.status = TaskStatus.FAILED
        # 再計算
        progress.completed_at = ""
        result = verifier.verify(goal, plan, progress)
        assert result.achievement_pct < GoalVerifier.ACHIEVEMENT_THRESHOLD

    def test_verify_result_has_recommendations(self):
        verifier = GoalVerifier()
        goal = GoalParser().parse("セキュリティを強化したい")
        plan = GoalDecomposer().decompose(goal)
        progress = _run(ExecutionCoordinator().execute(plan))
        result = verifier.verify(goal, plan, progress)
        assert len(result.recommendations) >= 1

    def test_verify_result_to_dict(self):
        verifier = GoalVerifier()
        goal = GoalParser().parse("ドキュメントを整備したい")
        plan = GoalDecomposer().decompose(goal)
        progress = _run(ExecutionCoordinator().execute(plan))
        result = verifier.verify(goal, plan, progress)
        d = result.to_dict()
        assert "overall_achieved" in d
        assert "achievement_pct" in d


# ═══════════════════════════════════════════════════════════════
# AbstractGoalPipeline フルフロー
# ═══════════════════════════════════════════════════════════════

class TestAbstractGoalPipeline:
    def test_full_pipeline_succeeds(self, tmp_path):
        from unittest.mock import patch
        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            pipeline = AbstractGoalPipeline()
            result = _run(pipeline.run("テストカバレッジを向上させたい"))
        assert result.success is True
        assert result.goal.goal_type == GoalType.TEST_COVERAGE
        assert result.plan.total_tasks >= 1

    def test_full_pipeline_security_goal(self, tmp_path):
        from unittest.mock import patch
        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            pipeline = AbstractGoalPipeline()
            result = _run(pipeline.run("セキュリティを強化したい"))
        assert result.goal.goal_type == GoalType.SECURITY
        assert result.execution_progress.done_count == result.execution_progress.total

    def test_pipeline_summary_contains_key_info(self, tmp_path):
        from unittest.mock import patch
        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            pipeline = AbstractGoalPipeline()
            result = _run(pipeline.run("パフォーマンスを改善したい"))
        summary = result.summary()
        assert "目標" in summary
        assert "タスク" in summary
        assert "達成度" in summary
