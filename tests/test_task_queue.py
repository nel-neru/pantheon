"""Tests for TaskQueue."""

import json
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


def test_get_pending_tasks_tolerates_null_priority_and_created_at(tmp_path):
    """priority/created_at が null の生 JSON タスク（legacy/手編集/外部）で drain ソートが落ちない。

    回帰: get_pending_tasks の ``-int(t.get("priority", 5))`` は null で ``int(None)`` TypeError、
    ``t.get("created_at", "")`` は null で ``None < str`` TypeError。これが try/except に包まれた
    24/7 デーモンの drain ループを静かに止めていた。加えて priority ``0`` は有効値なので
    ``value or 5`` 系の素朴な修正だと 0→5 に破壊される（``pending[-1] == "c"`` がそれを捕捉）。
    """
    queue_file = tmp_path / "queue.json"
    queue_file.write_text(
        json.dumps(
            {
                "version": 1,
                "tasks": [
                    # priority/created_at が null＝旧コードはここで int(None)/None<str クラッシュ
                    {"id": "a", "status": "pending", "priority": None, "created_at": None},
                    {"id": "b", "status": "pending", "priority": 9, "created_at": "2026-01-02"},
                    {"id": "c", "status": "pending", "priority": 0, "created_at": "2026-01-01"},
                    {"id": "d", "status": "pending", "priority": 3, "created_at": "2026-01-03"},
                ],
            }
        ),
        encoding="utf-8",
    )
    queue = TaskQueue(queue_file)

    pending = queue.get_pending_tasks(limit=None)  # 旧コードはソートキー算出で TypeError

    assert {t["id"] for t in pending} == {"a", "b", "c", "d"}
    # priority 9(b) が最優先、null(a)→default 5。priority 0(c) は 0 のまま＝-priority 順で最後尾。
    # 素朴な ``priority or 5`` だと c が 5 に化け d(3) より前に来て最後尾は d になる（差分検出）。
    assert pending[0]["id"] == "b"
    assert pending[-1]["id"] == "c"

    # list_tasks も created_at null で落ちない。
    listed = queue.list_tasks(limit=None)
    assert {t["id"] for t in listed} == {"a", "b", "c", "d"}


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


def test_cleanup_old_tasks_handles_naive_completed_at(tmp_path):
    # legacy/移行データで tz 情報のない completed_at を持つ完了タスクがあっても、
    # cleanup_old_tasks が naive>aware の TypeError でクラッシュせず正しく掃除する（回帰）。
    import json
    from datetime import datetime, timedelta, timezone

    queue_file = tmp_path / "queue.json"
    queue = TaskQueue(queue_file)
    recent = queue.add_task("analyze", "OrgA", "recent")
    old = queue.add_task("analyze", "OrgB", "old")
    queue.update_status(recent["id"], TaskStatus.DONE)
    queue.update_status(old["id"], TaskStatus.DONE)

    # completed_at を tz 情報なし（naive）の文字列へ書き換え、legacy データを模す
    data = json.loads(queue_file.read_text(encoding="utf-8"))
    naive_recent = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None).isoformat()
    naive_old = (datetime.now(timezone.utc) - timedelta(days=30)).replace(tzinfo=None).isoformat()
    assert "+" not in naive_recent and not naive_recent.endswith("Z")  # 確かに naive
    for t in data["tasks"]:
        if t["id"] == recent["id"]:
            t["completed_at"] = naive_recent
        elif t["id"] == old["id"]:
            t["completed_at"] = naive_old
    queue_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 旧コードでは naive>aware の比較で TypeError がここで送出された
    removed = queue.cleanup_old_tasks(keep_days=7)

    assert removed == 1  # old のみ削除、recent は keep_days(7日) 内なので残る
    remaining_ids = {t["id"] for t in queue.list_tasks(limit=None)}
    assert recent["id"] in remaining_ids
    assert old["id"] not in remaining_ids
