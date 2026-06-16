"""Tests for TaskQueue."""

import subprocess
import sys
import textwrap
from pathlib import Path

from core.orchestration.task_queue import TaskQueue, TaskStatus

_REPO_ROOT = Path(__file__).resolve().parents[1]


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


def test_task_queue_concurrent_cross_process_no_lost_update(tmp_path):
    """A second OS process adding tasks concurrently must not clobber this
    process's additions (load→modify→save lost-update). The in-process RLock
    cannot guard across processes — only the fcntl/msvcrt cross-process lock can,
    so this proves that lock actually serialises multi-process queue writes.

    Without a working cross-process lock (e.g. the old fcntl-only path that
    no-ops on Windows) the interleaved load/save loses some additions and the
    final count drops below parent+child.
    """
    queue_file = tmp_path / "queue.json"
    n_each = 60
    n_children = 3
    child_src = textwrap.dedent(
        f"""
        import sys
        from core.orchestration.task_queue import TaskQueue
        q = TaskQueue({str(queue_file)!r})
        tag = sys.argv[1]
        for i in range({n_each}):
            q.add_task("analyze", tag, f"{{tag}}-{{i}}")
        """
    )
    # Start the children first so their writes overlap the parent's loop. Enough
    # contention that, WITHOUT a real cross-process lock, the interleaved
    # load/save reliably loses updates (and concurrent os.replace vs. open even
    # crashes) — which is exactly what the lock must prevent.
    children = [
        subprocess.Popen(
            [sys.executable, "-c", child_src, f"Child{k}"],
            cwd=str(_REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for k in range(n_children)
    ]
    parent_queue = TaskQueue(queue_file)
    for i in range(n_each):
        parent_queue.add_task("analyze", "Parent", f"parent-{i}")

    for child in children:
        _, err = child.communicate(timeout=180)
        assert child.returncode == 0, f"child failed: {err.decode('utf-8', 'replace')}"

    tasks = parent_queue.list_tasks(limit=None)
    # every add from the parent and all children survived; nothing was clobbered
    assert len(tasks) == n_each * (n_children + 1)
    names = sorted(t["org_name"] for t in tasks)
    assert names.count("Parent") == n_each
    for k in range(n_children):
        assert names.count(f"Child{k}") == n_each
