"""作業ボードの headless 自動実行（共有 drain ヘルパ + ``task`` daemon）のテスト。

- ``core.runtime.task_drain.drain_pending_tasks`` — web GUI / CLI / daemon 共通の
  正準 drain（PENDING を ``work_launcher.dispatch_task`` 経由で着火）。
- ``core.runtime.task_drain_scheduler.TaskDrainScheduler`` — headless daemon。
  クォータ逼迫時はスキップ、着火件数を summary ログに残す。

実 wmux 着火は ``work_launcher.dispatch_task`` を fake に差し替えて回避し、その上の
実 executor 配線（PENDING→DONE）は本物を通す。
"""

from __future__ import annotations

from core.orchestration.task_queue import TaskQueue
from core.runtime.task_drain import drain_pending_tasks
from core.runtime.task_drain_scheduler import TaskDrainScheduler


class _FakeRecord:
    """``work_launcher.dispatch_task`` が返す SessionRecord の最小代役。"""

    def __init__(self, tid: str, driver: str = "headless"):
        self.id = f"sess-{tid}"
        self.driver = driver


class _AllowGov:
    def allow(self, priority, **_kw):
        return type("V", (), {"allowed": True})()


class _DenyGov:
    def allow(self, priority, **_kw):
        return type("V", (), {"allowed": False})()


def _patch_dispatch(monkeypatch):
    """実 wmux/サブプロセス着火を fake に差し替える（task→DONE の配線は本物を通す）。"""
    monkeypatch.setattr("core.runtime.work_launcher.dispatch_task", lambda t: _FakeRecord(t["id"]))


# --------------------------------------------------------------------------- #
# 共有ヘルパ drain_pending_tasks
# --------------------------------------------------------------------------- #


async def test_drain_helper_fires_and_marks_done(tmp_path, monkeypatch):
    _patch_dispatch(monkeypatch)
    queue = TaskQueue(queue_file=tmp_path / "task_queue.json")
    t1 = queue.add_task("goal", "", "やること1", priority=5)
    t2 = queue.add_task("goal", "", "やること2", priority=5)

    results = await drain_pending_tasks(queue=queue, max_tasks=10)

    # 2 件とも着火され（session_id 付き結果）、executor 経由で DONE になっている。
    fired = [r for r in results if isinstance(r, dict) and r.get("session_id")]
    assert len(fired) == 2
    assert {r["session_id"] for r in fired} == {f"sess-{t1['id']}", f"sess-{t2['id']}"}
    assert queue.get_pending_tasks(limit=None) == []
    assert queue.get_task(t1["id"])["status"] == "done"
    assert queue.get_task(t2["id"])["status"] == "done"


async def test_drain_helper_org_filter(tmp_path, monkeypatch):
    _patch_dispatch(monkeypatch)
    queue = TaskQueue(queue_file=tmp_path / "task_queue.json")
    keep = queue.add_task("analyze", "Alpha", "α のタスク", priority=5)
    skip = queue.add_task("analyze", "Beta", "β のタスク", priority=5)

    results = await drain_pending_tasks(queue=queue, org_filter="Alpha", max_tasks=10)

    fired = [r for r in results if isinstance(r, dict) and r.get("session_id")]
    assert len(fired) == 1
    assert fired[0]["session_id"] == f"sess-{keep['id']}"
    # フィルタ対象外は着火されず PENDING のまま残る。
    assert queue.get_task(keep["id"])["status"] == "done"
    assert queue.get_task(skip["id"])["status"] == "pending"


async def test_drain_helper_empty_returns_empty(tmp_path, monkeypatch):
    _patch_dispatch(monkeypatch)
    queue = TaskQueue(queue_file=tmp_path / "task_queue.json")
    results = await drain_pending_tasks(queue=queue, max_tasks=10)
    assert results == []


# --------------------------------------------------------------------------- #
# TaskDrainScheduler（headless daemon）
# --------------------------------------------------------------------------- #


async def test_scheduler_run_cycle_fires_pending(tmp_path, monkeypatch):
    monkeypatch.setattr("core.orchestration.task_queue.get_platform_home", lambda: tmp_path)
    _patch_dispatch(monkeypatch)
    TaskQueue().add_task("goal", "", "headless で実行されるべき", priority=5)

    sched = TaskDrainScheduler(platform_home=tmp_path, interval_seconds=120)
    # gate/governor は実 ~/.pantheon 状態に依存しないよう allow 固定で隔離する。
    sched._governor = _AllowGov()

    summary = await sched.run_cycle()

    assert summary["fired"] == 1
    assert summary["failed"] == 0
    assert "skipped_by_quota" not in summary
    assert TaskQueue().get_pending_tasks(limit=None) == []
    # summary は drain ログに永続化される（運用観測用）。
    logs = sched.get_recent_logs()
    assert logs and logs[-1]["fired"] == 1


async def test_scheduler_run_cycle_skipped_when_quota_tight(tmp_path, monkeypatch):
    monkeypatch.setattr("core.orchestration.task_queue.get_platform_home", lambda: tmp_path)
    _patch_dispatch(monkeypatch)
    task = TaskQueue().add_task("goal", "", "クォータ逼迫中は着火しない", priority=5)

    sched = TaskDrainScheduler(platform_home=tmp_path, interval_seconds=120)
    sched._governor = _DenyGov()  # background クォータ逼迫を模す

    summary = await sched.run_cycle()

    # 着火せずスキップ。タスクは PENDING のまま残る（無言で消費しない）。
    assert summary.get("skipped_by_quota") is True
    assert "fired" not in summary
    assert TaskQueue().get_task(task["id"])["status"] == "pending"


async def test_scheduler_run_cycle_counts_dispatch_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("core.orchestration.task_queue.get_platform_home", lambda: tmp_path)

    def _boom(_t):
        raise RuntimeError("wmux down")

    monkeypatch.setattr("core.runtime.work_launcher.dispatch_task", _boom)
    TaskQueue().add_task("goal", "", "着火に失敗する", priority=5)

    sched = TaskDrainScheduler(platform_home=tmp_path, interval_seconds=120)
    sched._governor = _AllowGov()

    summary = await sched.run_cycle()

    # 例外でループは落ちず、failed に計上される（健全な無着火と区別できる）。
    assert summary["fired"] == 0
    assert summary["failed"] >= 1
