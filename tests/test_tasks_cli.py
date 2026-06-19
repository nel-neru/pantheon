"""Tests for the `pantheon tasks` CLI handlers (commands.tasks).

headless 実行経路（GUI を開かなくてもキューを drain できる）を pin する。wmux は
実起動せず work_launcher.dispatch_task / launch_* を monkeypatch し、ハンドラが
グローバルタスクキューを正しく操作することを検証する。
"""

from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest

import commands.tasks as tasks
import core.orchestration.task_queue as task_queue_module
import core.runtime.work_launcher as work_launcher
from core.orchestration.task_queue import TaskQueue, TaskStatus, TaskType


def test_task_types_match_enum():
    """CLI の choices（TASK_TYPES）が TaskType enum とドリフトしないことを pin する。"""
    assert tasks.TASK_TYPES == tuple(t.value for t in TaskType)


@pytest.fixture
def queue_home(tmp_path, monkeypatch):
    monkeypatch.setattr(task_queue_module, "get_platform_home", lambda: tmp_path)
    return tmp_path


def _ns(**kw):
    return argparse.Namespace(**kw)


# --- work_launcher.dispatch_task（web/CLI 共通チョークポイント）の振り分け ---


def test_dispatch_task_routes_analyze_when_typed_and_org(monkeypatch):
    calls: list[tuple[str, tuple, dict]] = []

    def fake_analyze(org, **kw):
        calls.append(("analyze", (org,), kw))
        return SimpleNamespace(id="sess-a", driver="wmux")

    def fake_goal(text, **kw):
        calls.append(("goal", (text,), kw))
        return SimpleNamespace(id="sess-g", driver="wmux")

    monkeypatch.setattr(work_launcher, "launch_analyze", fake_analyze)
    monkeypatch.setattr(work_launcher, "launch_goal", fake_goal)

    rec = work_launcher.dispatch_task({"type": "analyze", "org_name": "Acme", "description": "x"})
    assert rec.id == "sess-a"
    assert calls == [("analyze", ("Acme",), {"repo_root": None, "prefer": None})]


def test_dispatch_task_routes_goal_otherwise(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        work_launcher,
        "launch_goal",
        lambda text, **kw: calls.append(text) or SimpleNamespace(id="sess-g", driver="wmux"),
    )
    # org 無しの analyze は goal にフォールバック（type 条件は org_name も要求する）。
    rec = work_launcher.dispatch_task({"type": "analyze", "description": "解析して"})
    assert rec.id == "sess-g"
    assert calls == ["解析して"]


# --- pantheon tasks add / list / drain ---


async def test_tasks_add_enqueues_pending(queue_home, capsys):
    await tasks.cmd_tasks_add(_ns(type="goal", org="Acme", description="新機能を作る", priority=7))
    out = capsys.readouterr().out
    assert "積みました" in out

    pending = TaskQueue().get_pending_tasks(limit=None)
    assert len(pending) == 1
    assert pending[0]["type"] == "goal"
    assert pending[0]["priority"] == 7
    assert pending[0]["org_name"] == "Acme"


async def test_tasks_add_requires_org_for_analyze(queue_home, capsys):
    """analyze/review/improve は --org 必須（org 無しの無言 goal フォールバックを防ぐ）。"""
    await tasks.cmd_tasks_add(_ns(type="analyze", org=None, description="解析して", priority=5))
    out = capsys.readouterr().out
    assert "エラー" in out
    # キューには積まれていない。
    assert TaskQueue().list_tasks(limit=None) == []


async def test_tasks_list_prints_rows_and_count(queue_home, capsys):
    q = TaskQueue()
    q.add_task("analyze", "Acme", "解析A", priority=3)
    q.add_task("goal", "Beta", "目標B", priority=5)

    await tasks.cmd_tasks_list(_ns(org=None, status=None))
    out = capsys.readouterr().out
    assert "解析A" in out
    assert "目標B" in out
    assert "計 2 件" in out


async def test_tasks_list_empty(queue_home, capsys):
    await tasks.cmd_tasks_list(_ns(org=None, status=None))
    assert "タスクはありません。" in capsys.readouterr().out


async def test_tasks_drain_dispatches_pending(queue_home, monkeypatch, capsys):
    q = TaskQueue()
    t1 = q.add_task("goal", "Acme", "目標1", priority=5)
    t2 = q.add_task("goal", "Beta", "目標2", priority=8)

    def fake_dispatch(task, **kw):
        return SimpleNamespace(id=f"sess-{task['id'][:4]}", driver="wmux")

    monkeypatch.setattr(work_launcher, "dispatch_task", fake_dispatch)

    await tasks.cmd_tasks_drain(_ns(org=None, max_tasks=10))
    out = capsys.readouterr().out

    assert "着火 2 件" in out
    # 両タスクが executor 経由で DONE になり、保留が捌けている。
    assert TaskQueue().get_pending_tasks(limit=None) == []
    assert TaskQueue().get_task(t1["id"])["status"] == TaskStatus.DONE.value
    assert TaskQueue().get_task(t2["id"])["status"] == TaskStatus.DONE.value


async def test_tasks_drain_respects_org_filter(queue_home, monkeypatch, capsys):
    q = TaskQueue()
    keep = q.add_task("goal", "Acme", "Acmeの目標", priority=5)
    other = q.add_task("goal", "Beta", "Betaの目標", priority=5)

    monkeypatch.setattr(
        work_launcher,
        "dispatch_task",
        lambda task, **kw: SimpleNamespace(id="sess-x", driver="wmux"),
    )

    await tasks.cmd_tasks_drain(_ns(org="Acme", max_tasks=10))
    capsys.readouterr()

    # Acme だけ着火され、Beta は PENDING のまま残る。
    assert TaskQueue().get_task(keep["id"])["status"] == TaskStatus.DONE.value
    assert TaskQueue().get_task(other["id"])["status"] == TaskStatus.PENDING.value


async def test_tasks_drain_no_pending(queue_home, monkeypatch, capsys):
    monkeypatch.setattr(
        work_launcher,
        "dispatch_task",
        lambda task, **kw: SimpleNamespace(id="sess-x", driver="wmux"),
    )
    await tasks.cmd_tasks_drain(_ns(org=None, max_tasks=10))
    assert "着火対象の保留タスクはありません。" in capsys.readouterr().out
