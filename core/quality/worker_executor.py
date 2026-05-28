"""
SpecialistWorker 実行 + Strict Review + 永続化 の統合実行レイヤー

ワーカーが何かを実行する際に、自動でInternal Consultantによる
厳格レビュー → .repocorp/ 永続化 までを一貫して行う。
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from core.models.organization import SpecialistAgent
from core.quality.internal_consultant import run_strict_quality_review
from core.quality.trigger import generate_improvement_proposals_from_review
from core.state.manager import RepoStateManager


class WorkerTaskExecutor:
    """
    SpecialistWorker用の実行ラッパー。
    タスク実行 → 厳格レビュー → 改善提案生成 → .repocorp/保存 を自動化。
    """

    def __init__(self, state_manager: RepoStateManager, worker: SpecialistAgent):
        self.state_manager = state_manager
        self.worker = worker

    async def execute_with_full_review(
        self,
        task_func: Callable[[], Awaitable[Any]],
        task_description: str,
        thinking_process: str = "",
        execution_log: str = "",
        output_summary: str = "",
        cost_info: Optional[dict] = None,
        context: Optional[str] = None,
    ):
        """
        ワーカーがタスクを実行し、自動で厳格レビュー＋永続化まで行う
        """
        print(f"[WorkerExecutor] {self.worker.name} がタスクを開始: {task_description[:50]}...")

        # 1. タスク実行（ここにワーカーの実際のロジックが入る想定）
        result = await task_func()

        # 2. 厳格レビュー実行
        review = await run_strict_quality_review(
            task_description=task_description,
            thinking_process=thinking_process or f"{self.worker.name} の思考プロセス",
            execution_log=execution_log or f"Executed by {self.worker.name}",
            output_summary=output_summary or str(result)[:400],
            cost_info=cost_info,
            context=context,
        )

        # 3. 改善提案生成
        proposals = generate_improvement_proposals_from_review(review)

        # 4. .repocorp/ に永続化
        self.state_manager.save_quality_review(review)
        for proposal in proposals:
            self.state_manager.save_improvement_proposal(proposal)

        print(f"[WorkerExecutor] レビュー完了 (Score: {review.overall_score:.1f}) / 提案 {len(proposals)}件 保存済み")

        return result, review, proposals
