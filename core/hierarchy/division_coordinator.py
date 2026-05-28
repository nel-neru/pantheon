"""
DivisionCoordinator — Division間協調タスク実行 (E-06)
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass
class CrossDivisionTask:
    task_id: str
    description: str
    divisions_involved: list[str]
    status: str = "pending"


class DivisionCoordinator:
    def __init__(self):
        self._tasks: list[CrossDivisionTask] = []

    def assign_divisions(self, task_description: str, available_divisions: list[str]) -> list[str]:
        lower_description = task_description.lower()
        if "architecture" in lower_description:
            preferred = ["Engineering", "Architecture"]
        elif "security" in lower_description:
            preferred = ["Security", "Engineering"]
        elif "test" in lower_description:
            preferred = ["QA", "Engineering"]
        else:
            preferred = available_divisions[:2]

        selected = [division for division in preferred if division in available_divisions]
        for division in available_divisions:
            if division not in selected:
                selected.append(division)
            if len(selected) >= min(2, len(available_divisions)):
                break
        return selected[: min(2, len(selected))]

    def create_cross_task(self, description: str, divisions: list[str]) -> CrossDivisionTask:
        task = CrossDivisionTask(
            task_id=f"cross-task:{uuid4()}",
            description=description,
            divisions_involved=list(divisions),
        )
        self._tasks.append(task)
        return task

    def get_task_summary(self, task: CrossDivisionTask) -> str:
        return f"[{task.status}] {task.description} ({', '.join(task.divisions_involved)})"
