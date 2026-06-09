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
                result_summary, success, error = await self._run_via_orchestrator(task)
                if success:
                    task_prog.status = TaskStatus.DONE
                    task_prog.result_summary = result_summary
                    task_prog.completed_at = datetime.now(timezone.utc).isoformat()
                    self._notify(progress)
                    return
                raise RuntimeError(error or "タスク実行に失敗しました")

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

    async def _run_via_orchestrator(self, task: TaskSpec) -> tuple[str, bool, str]:
        """タスクを実行し ``(result_summary, success, error)`` を返す。

        オーケストレーターに実行バックエンド（agent_factory）が配線されていれば
        **実エージェントを実行**して結果を反映する。配線が無い最小構成では従来どおり
        計画（TaskAnalysis）のみを生成して完了扱いにする（後方互換）。
        """
        if not self._orchestrator:
            return (f"直接実行（オーケストレーターなし）: {task.title}", True, "")

        analysis = self._orchestrator.analyze(task.agent_type, task.description)

        # 実行は「推奨エージェントがある」かつ「orchestrator.execute が使える」時のみ。
        # それ以外（能力未登録の最小構成 / execute 非対応のモック）は計画のみ完了扱い。
        recommended = getattr(analysis, "recommended_agent_ids", None) or []
        execute_fn = getattr(self._orchestrator, "execute", None)
        if not recommended or not callable(execute_fn):
            return (self._plan_only_summary(analysis), True, "")

        agent_task = self._build_agent_task(task)
        result = await execute_fn(agent_task, analysis)

        # agent_factory が無いと execute() は渡した analysis をそのまま返す（計画のみ）。
        if result is analysis:
            return (self._plan_only_summary(analysis), True, "")

        # それ以外は AgentResult。成否を反映する。
        if getattr(result, "success", False):
            return (self._summarize_agent_result(result, analysis), True, "")

        # 実行バックエンドがエージェントを起動できないだけのケースは計画のみ完了扱いにし、
        # 実際にエージェントが走って失敗した場合のみ FAILED とする。
        error = str(getattr(result, "error", "unknown error"))
        if any(token in error for token in ("No agent selected", "Agent not found")):
            return (self._plan_only_summary(analysis), True, "")
        return ("", False, error)

    @staticmethod
    def _plan_only_summary(analysis: Any) -> str:
        return (
            f"計画のみ（実行バックエンド未配線）: パターン "
            f"{getattr(analysis, 'recommended_pattern', '?')}, "
            f"エージェント {getattr(analysis, 'recommended_agent_ids', [])}"
        )

    @staticmethod
    def _build_agent_task(task: TaskSpec):
        from agents.base import AgentTask as _AgentTask

        return _AgentTask(
            task_type=task.agent_type,
            description=task.description,
            input={"task_id": task.task_id, "title": task.title},
        )

    @staticmethod
    def _summarize_agent_result(result: Any, analysis: Any) -> str:
        output = getattr(result, "output", {}) or {}
        summary = output.get("change_summary") or output.get("summary")
        if summary:
            return str(summary)
        return f"実行完了（パターン: {getattr(analysis, 'recommended_pattern', '?')}）"

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
