import asyncio

from core.orchestration.multi_org_executor import MultiOrgExecutor
from core.orchestration.task_queue import TaskQueue, TaskStatus


def test_multi_org_executor_processes_pending_tasks(tmp_path):
    queue = TaskQueue(tmp_path / "queue.json")
    queue.add_task("analyze", "OrgA", "タスクA", priority=3)
    queue.add_task("analyze", "OrgB", "タスクB", priority=8)

    executor = MultiOrgExecutor(max_concurrent=2, queue=queue)

    async def run_task(task):
        return {"task_id": task["id"], "org_name": task["org_name"]}

    results = asyncio.run(executor.process_pending(run_task, max_tasks=2))

    assert len(results) == 2
    assert {result["org_name"] for result in results} == {"OrgA", "OrgB"}
    assert queue.get_pending_tasks(limit=None) == []
    assert all(queue.get_task(result["task_id"])["status"] == TaskStatus.DONE for result in results)
