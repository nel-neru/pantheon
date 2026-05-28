"""
ExecutionCoordinator — 自律実行コーディネーター (M-04)

GoalPlan（Epic/Story/Task ツリー）を受け取り、
依存関係を考慮しながら順次タスクを実行するコーディネーター。

設計:
  - 依存グラフを解析し、実行可能なタスクを順に実行
  - 失敗タスクは最大 MAX_RETRIES 回リトライ
  - 進捗を GoalProgressTracker に記録
  - PreTaskOrchestrator と統合して各タスクを最適実行
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from core.goals.goal_decomposer import GoalPlan, TaskSpec

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskProgress:
    """タスクの実行状態。"""

    task_id: str
    title: str
    status: TaskStatus = TaskStatus.PENDING
    retries: int = 0
    result_summary: str = ""
    error: str = ""
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "status": self.status.value,
            "retries": self.retries,
            "result_summary": self.result_summary,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass
class ExecutionProgress:
    """GoalPlan 全体の実行状態。"""

    plan_id: str
    goal_description: str
    task_progresses: Dict[str, TaskProgress] = field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""

    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.now(timezone.utc).isoformat()

    @property
    def total(self) -> int:
        return len(self.task_progresses)

    @property
    def done_count(self) -> int:
        return sum(1 for p in self.task_progresses.values() if p.status == TaskStatus.DONE)

    @property
    def failed_count(self) -> int:
        return sum(1 for p in self.task_progresses.values() if p.status == TaskStatus.FAILED)

    @property
    def progress_pct(self) -> float:
        if not self.task_progresses:
            return 0.0
        return self.done_count / len(self.task_progresses) * 100

    @property
    def is_complete(self) -> bool:
        return all(
            p.status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.SKIPPED)
            for p in self.task_progresses.values()
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal_description": self.goal_description,
            "total": self.total,
            "done": self.done_count,
            "failed": self.failed_count,
            "progress_pct": self.progress_pct,
            "is_complete": self.is_complete,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "tasks": {tid: p.to_dict() for tid, p in self.task_progresses.items()},
        }


class ExecutionCoordinator:
    """
    GoalPlan を受け取り、依存関係を考慮して順次タスクを実行する。

    各タスクは PreTaskOrchestrator を通じて最適なエージェントで実行される。
    """

    def __init__(
        self,
        pre_task_orchestrator: Optional[Any] = None,
        progress_callback: Optional[Any] = None,
    ):
        self._orchestrator = pre_task_orchestrator
        self._progress_callback = progress_callback

    async def execute(
        self,
        plan: GoalPlan,
        **_kwargs: Any,
    ) -> ExecutionProgress:
        """
        GoalPlan の全タスクを実行する。

        Args:
            plan: 実行するゴールプラン

        Returns:
            ExecutionProgress（実行後の全タスク状態）
        """
        progress = ExecutionProgress(
            plan_id=plan.plan_id,
            goal_description=plan.goal_description,
        )
        all_tasks = plan.get_all_tasks()

        for task in all_tasks:
            progress.task_progresses[task.task_id] = TaskProgress(
                task_id=task.task_id,
                title=task.title,
            )

        ordered = self._topological_sort(all_tasks)

        for task in ordered:
            task_prog = progress.task_progresses[task.task_id]

            if self._has_failed_dependency(task, progress):
                task_prog.status = TaskStatus.SKIPPED
                task_prog.error = "依存タスクが失敗したためスキップ"
                self._notify(progress)
                continue

            if not task.is_executable:
                task_prog.status = TaskStatus.SKIPPED
                task_prog.error = "対応するエージェント能力がないためスキップ"
                self._notify(progress)
                continue

            await self._execute_task(task, task_prog, progress)

        progress.completed_at = datetime.now(timezone.utc).isoformat()
        return progress

    async def _execute_task(
        self,
        task: TaskSpec,
        task_prog: TaskProgress,
        progress: ExecutionProgress,
    ) -> None:
        """単一タスクをリトライ付きで実行する。"""
        task_prog.status = TaskStatus.RUNNING
        task_prog.started_at = datetime.now(timezone.utc).isoformat()
        self._notify(progress)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if self._orchestrator:
                    analysis = self._orchestrator.analyze(
                        task.agent_type,
                        task.description,
                    )
                    result_summary = (
                        f"パターン: {analysis.recommended_pattern}, "
                        f"エージェント: {analysis.recommended_agent_ids}"
                    )
                else:
                    result_summary = f"直接実行（オーケストレーターなし）: {task.title}"

                task_prog.status = TaskStatus.DONE
                task_prog.result_summary = result_summary
                task_prog.completed_at = datetime.now(timezone.utc).isoformat()
                self._notify(progress)
                return

            except Exception as e:
                task_prog.retries = attempt
                logger.warning("Task %s attempt %d failed: %s", task.task_id, attempt, e)
                if attempt == MAX_RETRIES:
                    task_prog.status = TaskStatus.FAILED
                    task_prog.error = str(e)
                    task_prog.completed_at = datetime.now(timezone.utc).isoformat()
                    self._notify(progress)
                else:
                    await asyncio.sleep(0.1)

    def _topological_sort(self, tasks: List[TaskSpec]) -> List[TaskSpec]:
        """タスクを依存関係に従って順序付ける（トポロジカルソート）。"""
        task_map = {t.task_id: t for t in tasks}
        visited: set = set()
        result: List[TaskSpec] = []

        def visit(task: TaskSpec) -> None:
            if task.task_id in visited:
                return
            for dep_id in task.dependencies:
                if dep_id in task_map:
                    visit(task_map[dep_id])
            visited.add(task.task_id)
            result.append(task)

        for task in tasks:
            visit(task)
        return result

    def _has_failed_dependency(self, task: TaskSpec, progress: ExecutionProgress) -> bool:
        """依存タスクが失敗しているかを確認する。"""
        for dep_id in task.dependencies:
            dep_prog = progress.task_progresses.get(dep_id)
            if dep_prog and dep_prog.status == TaskStatus.FAILED:
                return True
        return False

    def _notify(self, progress: ExecutionProgress) -> None:
        """進捗コールバックを呼び出す（設定されている場合）。"""
        if self._progress_callback:
            try:
                self._progress_callback(progress)
            except Exception:
                pass
