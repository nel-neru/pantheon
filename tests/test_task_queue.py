"""Tests for TaskQueue."""

from core.orchestration.task_queue import TaskQueue, TaskStatus


def test_task_queue_add_and_get(tmp_path):
    queue = TaskQueue(tmp_path / "queue.json")

    task = queue.add_task("analyze", "TestOrg", "テスト分析")

    assert task["status"] == TaskStatus.PENDING
    assert task["org_name"] == "TestOrg"

    fetched = queue.get_task(task["id"])
    assert fetched is not None
    assert fetched["id"] == task["id"]


def test_task_queue_status_update(tmp_path):
    queue = TaskQueue(tmp_path / "queue.json")

    task = queue.add_task("analyze", "TestOrg", "テスト")
    queue.update_status(task["id"], TaskStatus.RUNNING)

    fetched = queue.get_task(task["id"])
    assert fetched is not None
    assert fetched["status"] == TaskStatus.RUNNING
    assert fetched["started_at"] is not None


def test_task_queue_cancel(tmp_path):
    queue = TaskQueue(tmp_path / "queue.json")

    task = queue.add_task("analyze", "TestOrg", "テスト")
    success = queue.cancel_task(task["id"])

    assert success is True
    fetched = queue.get_task(task["id"])
    assert fetched is not None
    assert fetched["status"] == TaskStatus.CANCELLED


def test_task_queue_list_filter(tmp_path):
    queue = TaskQueue(tmp_path / "queue.json")

    queue.add_task("analyze", "OrgA", "タスク1")
    queue.add_task("analyze", "OrgB", "タスク2")

    org_a_tasks = queue.list_tasks(org_name="OrgA")
    assert len(org_a_tasks) == 1
    assert org_a_tasks[0]["org_name"] == "OrgA"


def test_task_queue_pending_priority_order(tmp_path):
    queue = TaskQueue(tmp_path / "queue.json")

    low = queue.add_task("analyze", "OrgA", "低優先度", priority=1)
    high = queue.add_task("analyze", "OrgB", "高優先度", priority=9)

    pending = queue.get_pending_tasks(limit=None)

    assert [task["id"] for task in pending][:2] == [high["id"], low["id"]]
