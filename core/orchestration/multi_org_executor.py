"""複数組織のタスクを並行実行するエグゼキューター。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine

from .task_queue import TaskQueue, TaskStatus

logger = logging.getLogger(__name__)

ExecutorFn = Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]


class MultiOrgExecutor:
    """複数組織のタスクを並行実行する。"""

    def __init__(self, max_concurrent: int = 5, queue: TaskQueue | None = None):
        self.max_concurrent = max_concurrent
        self.queue = queue or TaskQueue()
        self._running: dict[str, asyncio.Task[Any]] = {}

    async def execute_task(self, task: dict[str, Any], executor_fn: ExecutorFn) -> dict[str, Any]:
        """単一タスクを実行してキューを更新する。"""
        task_id = task["id"]
        current = asyncio.current_task()
        if current is not None:
            self._running[task_id] = current

        self.queue.update_status(task_id, TaskStatus.RUNNING)
        logger.info("[MultiOrgExecutor] Starting task %s: %s", task_id, task["description"])

        try:
            result = await executor_fn(task)
            self.queue.update_status(task_id, TaskStatus.DONE, result=result)
            logger.info("[MultiOrgExecutor] Task %s completed", task_id)
            return result
        except asyncio.CancelledError:
            self.queue.update_status(task_id, TaskStatus.CANCELLED, error="キャンセルされました")
            logger.info("[MultiOrgExecutor] Task %s cancelled", task_id)
            raise
        except Exception as exc:
            error_msg = str(exc)
            self.queue.update_status(task_id, TaskStatus.FAILED, error=error_msg)
            logger.error("[MultiOrgExecutor] Task %s failed: %s", task_id, error_msg)
            return {"error": error_msg}
        finally:
            self._running.pop(task_id, None)

    async def run_parallel(self, tasks: list[dict[str, Any]], executor_fn: ExecutorFn) -> list[dict[str, Any]]:
        """複数タスクを並行実行する（max_concurrent まで同時に実行）。"""
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def run_with_semaphore(task: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await self.execute_task(task, executor_fn)

        results = await asyncio.gather(
            *[run_with_semaphore(task) for task in tasks],
            return_exceptions=False,
        )
        return list(results)

    async def process_pending(
        self,
        executor_fn: ExecutorFn,
        org_filter: str | None = None,
        max_tasks: int = 10,
    ) -> list[dict[str, Any]]:
        """PENDINGタスクを取得して並行実行する。"""
        pending = self.queue.get_pending_tasks(limit=max_tasks)
        if org_filter:
            pending = [task for task in pending if task.get("org_name") == org_filter]

        if not pending:
            return []

        logger.info("[MultiOrgExecutor] Processing %s pending tasks", len(pending))
        return await self.run_parallel(pending, executor_fn)

    def cancel_running_task(self, task_id: str) -> bool:
        task = self._running.get(task_id)
        if task is None:
            return False
        task.cancel()
        return True
