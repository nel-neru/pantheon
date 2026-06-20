"""
GoalScheduler — 複数目標並列管理 (M-08)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class GoalExecution:
    execution_id: str
    goal_type: str
    description: str
    status: str = "pending"
    started_at: str = ""
    completed_at: str = ""


class GoalScheduler:
    """Track multiple goal executions with a simple in-memory queue."""

    def __init__(self, max_parallel: int = 3):
        self.max_parallel = max_parallel
        self._executions: list[GoalExecution] = []

    def submit_goal(self, goal_type: str, description: str) -> GoalExecution:
        # started_at は「実行開始時刻」。submit 時点は status="pending"（未実行）なので
        # ここでは刻まない（誤って投入時刻が実行開始時刻として記録され、タイミング分析が
        # 狂うのを防ぐ）。実行開始時に start_execution() で刻む。
        execution = GoalExecution(
            execution_id=f"exec:{uuid4().hex[:8]}",
            goal_type=goal_type,
            description=description,
        )
        self._executions.append(execution)
        return execution

    def start_execution(self, execution_id: str) -> bool:
        """対象を running に遷移し、実行開始時刻（started_at）を刻む。見つからなければ False。"""
        for execution in self._executions:
            if execution.execution_id == execution_id:
                execution.status = "running"
                execution.started_at = datetime.now(timezone.utc).isoformat()
                return True
        return False

    def complete_execution(self, execution_id: str, *, status: str = "completed") -> bool:
        """対象を終了状態に遷移し、完了時刻（completed_at）を刻む。見つからなければ False。"""
        for execution in self._executions:
            if execution.execution_id == execution_id:
                execution.status = status
                execution.completed_at = datetime.now(timezone.utc).isoformat()
                return True
        return False

    def get_active_executions(self) -> list[GoalExecution]:
        return [
            execution
            for execution in self._executions
            if execution.status in {"pending", "running"}
        ]

    def can_start_new(self) -> bool:
        return len(self.get_active_executions()) < self.max_parallel

    def get_status_summary(self) -> str:
        counts: dict[str, int] = {}
        for execution in self._executions:
            counts[execution.status] = counts.get(execution.status, 0) + 1
        if not counts:
            return "No goal executions scheduled."
        return ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))
