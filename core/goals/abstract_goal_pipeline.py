"""
AbstractGoalPipeline — 抽象目標→自律実行パイプライン (M-01~M-07)

開発者は「何を作りたいか」だけ伝えればあとはシステムが自律実行する。

フロー:
  1. GoalParser.parse()      — 自然言語 → StructuredGoal
  2. GoalDecomposer.decompose() — StructuredGoal → GoalPlan (Epic/Story/Task)
  3. OrgInstantiator.instantiate() — GoalPlan → Organization
  4. ExecutionCoordinator.execute() — GoalPlan を自律実行
  5. GoalVerifier.verify()   — 達成度を評価して推奨事項を返す
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from core.goals.execution_coordinator import ExecutionCoordinator, ExecutionProgress
from core.goals.goal_decomposer import GoalDecomposer, GoalPlan
from core.goals.goal_parser import GoalParser, StructuredGoal
from core.goals.goal_verifier import GoalVerificationResult, GoalVerifier
from core.goals.org_instantiator import InstantiationResult, OrgInstantiator

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """AbstractGoalPipeline の最終結果。"""

    raw_text: str
    goal: StructuredGoal
    plan: GoalPlan
    org_result: InstantiationResult
    execution_progress: ExecutionProgress
    verification: GoalVerificationResult

    @property
    def success(self) -> bool:
        return self.verification.overall_achieved

    def summary(self) -> str:
        lines = [
            f"目標: {self.goal.description}",
            f"種別: {self.goal.goal_type}  スケール: {self.goal.scale}",
            f"Organization: {self.org_result.organization.name} ({'新規' if self.org_result.is_new else '流用'})",
            f"タスク: {self.execution_progress.done_count}/{self.execution_progress.total} 完了 (失敗: {self.execution_progress.failed_count})",
            f"達成度: {self.verification.achievement_pct:.1f}% ({'✅ 達成' if self.success else '⚠️ 未達成'})",
        ]
        if self.verification.recommendations:
            lines.append("推奨事項:")
            for rec in self.verification.recommendations[:3]:
                lines.append(f"  {rec}")
        return "\n".join(lines)


class AbstractGoalPipeline:
    """
    抽象目標テキストを受け取り、M-01〜M-05 を順に実行して
    自律的にタスクを実行・達成検証するパイプライン。

    全コンポーネントが疎結合で、それぞれ差し替え可能。
    """

    def __init__(
        self,
        parser: Optional[GoalParser] = None,
        decomposer: Optional[GoalDecomposer] = None,
        instantiator: Optional[OrgInstantiator] = None,
        coordinator: Optional[ExecutionCoordinator] = None,
        verifier: Optional[GoalVerifier] = None,
        pre_task_orchestrator: Optional[Any] = None,
    ):
        self._parser = parser or GoalParser()
        self._decomposer = decomposer or GoalDecomposer()
        self._instantiator = instantiator or OrgInstantiator()
        # 既定で pattern_store 付き PreTaskOrchestrator を配線し、ゴール実行が
        # パターン学習として蓄積されるようにする（明示注入があればそれを優先）。
        if pre_task_orchestrator is None:
            try:
                from core.orchestration.orchestration_pattern_store import (
                    OrchestrationPatternStore,
                )
                from core.orchestration.pre_task_orchestrator import PreTaskOrchestrator

                pre_task_orchestrator = PreTaskOrchestrator(
                    pattern_store=OrchestrationPatternStore()
                )
            except Exception:  # noqa: BLE001 - 最小環境では従来どおり None で続行
                pre_task_orchestrator = None
        self._coordinator = coordinator or ExecutionCoordinator(
            pre_task_orchestrator=pre_task_orchestrator
        )
        self._verifier = verifier or GoalVerifier()

    async def run(
        self,
        raw_goal_text: str,
        use_llm: bool = False,
        **_kwargs: Any,
    ) -> PipelineResult:
        """
        自然言語の目標テキストからフルパイプラインを実行する。

        Args:
            raw_goal_text: 開発者が入力する自然言語の目標
            use_llm: LLM による高精度パース・分解を行うか

        Returns:
            PipelineResult
        """
        logger.info("AbstractGoalPipeline: starting for '%s'", raw_goal_text[:60])

        goal = self._parser.parse(raw_goal_text, use_llm=use_llm)
        logger.info("Goal parsed: type=%s, scale=%s", goal.goal_type, goal.scale)

        plan = self._decomposer.decompose(goal, use_llm=use_llm)
        logger.info("Plan created: %d epics, %d tasks", len(plan.epics), plan.total_tasks)

        org_result = self._instantiator.instantiate(goal)
        logger.info(
            "Organization: %s (%s)",
            org_result.organization.name,
            "new" if org_result.is_new else "reused",
        )

        progress = await self._coordinator.execute(plan)
        logger.info(
            "Execution complete: %d/%d done, %d failed",
            progress.done_count,
            progress.total,
            progress.failed_count,
        )

        verification = self._verifier.verify(goal, plan, progress, use_llm=use_llm)
        logger.info(
            "Verification: %.1f%% achieved (%s)",
            verification.achievement_pct,
            "achieved" if verification.overall_achieved else "not achieved",
        )

        return PipelineResult(
            raw_text=raw_goal_text,
            goal=goal,
            plan=plan,
            org_result=org_result,
            execution_progress=progress,
            verification=verification,
        )
