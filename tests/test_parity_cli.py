"""CLI↔Web パリティ CLI（content / publish jobs / inbox）の検証。

「WEB と同じ機能を CLI/自律から使う」ための追加コマンドが配線され、最小の振る舞いを満たすことを確認する。
外部送信や LLM 生成は行わず、ストア・ハンドラ・パーサ配線レベルで検証する。
"""

from __future__ import annotations

import argparse

import pytest

from commands import build_parser


def test_parity_cli_wired():
    """content / publish jobs / inbox の各サブコマンドが parser と HANDLERS に配線済み。"""
    import main

    parser = build_parser()
    cases = {
        ("content", "list"): "cmd_content_list",
        ("content", "run", "abc"): "cmd_content_run",
        ("content", "delete", "abc"): "cmd_content_delete",
        ("inbox", "list"): "cmd_inbox_list",
        ("publish", "jobs", "list"): "cmd_publish_jobs_list",
        ("publish", "jobs", "run", "abc"): "cmd_publish_jobs_run",
        ("publish", "jobs", "confirm", "abc"): "cmd_publish_jobs_confirm",
    }
    for argv, handler in cases.items():
        ns = parser.parse_args(list(argv))
        assert ns.handler_name == handler
        assert handler in main.HANDLERS, f"{handler} not in HANDLERS"

    # content create に必要な引数も配線されている
    create = parser.parse_args(
        ["content", "create", "--org", "X", "--kind", "short_video", "--theme", "T"]
    )
    assert create.handler_name == "cmd_content_create"


async def test_content_cli_crud(tmp_path, monkeypatch):
    """create でジョブが作られ、list/enable/disable/delete が機能する（P1）。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    from core.content.content_jobs import ContentJobStore
    from core.org_factory import create_default_organization
    from core.platform.state import PlatformStateManager

    # repo 紐づきの org を用意する（content_runner の生成先）。
    psm = PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("WS Co", "テスト")
    org.target_repo_path = str(tmp_path / "repo")
    psm.save_organization(org)

    from commands.content import (
        cmd_content_create,
        cmd_content_delete,
        cmd_content_disable,
        cmd_content_enable,
    )

    await cmd_content_create(
        argparse.Namespace(
            org="WS Co",
            kind="short_video",
            theme="AIツール紹介",
            interval=3600,
            platform="",
            mode="assisted",
            disabled=False,
        )
    )
    jobs = ContentJobStore(platform_home=tmp_path).list_jobs()
    assert len(jobs) == 1 and jobs[0].kind == "short_video" and jobs[0].org_name == "WS Co"
    jid = jobs[0].job_id

    await cmd_content_disable(argparse.Namespace(job_id=jid))
    assert ContentJobStore(platform_home=tmp_path).get_job(jid).enabled is False
    await cmd_content_enable(argparse.Namespace(job_id=jid))
    assert ContentJobStore(platform_home=tmp_path).get_job(jid).enabled is True

    await cmd_content_delete(argparse.Namespace(job_id=jid))
    assert ContentJobStore(platform_home=tmp_path).get_job(jid) is None


async def test_content_create_rejects_unknown_org(tmp_path, monkeypatch):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    from commands.content import cmd_content_create

    with pytest.raises(SystemExit):
        await cmd_content_create(
            argparse.Namespace(
                org="No Such Org",
                kind="content_brief",
                theme="",
                interval=3600,
                platform="",
                mode="assisted",
                disabled=False,
            )
        )


async def test_publish_jobs_cli_list_and_guards(tmp_path, monkeypatch):
    """publish jobs list/delete と、handed_off の run 拒否ガード（P3）。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    from core.publishing.publish_jobs import PublishJob, PublishJobStore

    store = PublishJobStore(platform_home=tmp_path)
    handed = store.add_job(
        PublishJob(org_name="Co", platform="note", title="記事A", status="handed_off")
    )
    queued = store.add_job(PublishJob(org_name="Co", platform="x", title="ポストB"))

    from commands.publish import (
        cmd_publish_jobs_confirm,
        cmd_publish_jobs_delete,
        cmd_publish_jobs_list,
    )

    # list は落ちずに動く（出力は内容に依存しないので例外が出ないことを確認）
    await cmd_publish_jobs_list(argparse.Namespace(status=None, org_name=None))

    # handed_off ジョブの run は再実行ガードで止まる
    from commands.publish import cmd_publish_jobs_run

    with pytest.raises(SystemExit):
        await cmd_publish_jobs_run(argparse.Namespace(job_id=handed.job_id, dry_run=False))

    # queued（handed_off でない）ジョブの confirm は ok=False → SystemExit
    with pytest.raises(SystemExit):
        await cmd_publish_jobs_confirm(argparse.Namespace(job_id=queued.job_id, url=""))

    # delete は機能する
    await cmd_publish_jobs_delete(argparse.Namespace(job_id=queued.job_id))
    assert store.get_job(queued.job_id) is None


def test_inbox_aggregates_human_tasks_and_proposals(tmp_path, monkeypatch):
    """_collect_inbox が人間タスク等を統合キューへ集約する（P2・GUI /inbox と同じ集約）。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    from core.humans.human_tasks import enqueue_human_task

    enqueue_human_task(
        "価格を承認する", platform_home=tmp_path, kind="company_setup", org_name="Co"
    )

    from commands.inbox import _collect_inbox

    items = _collect_inbox(tmp_path)
    human = [i for i in items if i["kind"] == "human_task"]
    assert any("価格を承認" in i["title"] for i in human)


async def test_inbox_list_category_and_impact_filters(tmp_path, monkeypatch, capsys):
    """inbox list の --category / --min-impact フィルタ（finding 16）。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    from commands.inbox import _collect_inbox, cmd_inbox_list
    from core.humans.human_tasks import enqueue_human_task

    enqueue_human_task("承認して", platform_home=tmp_path, kind="company_setup", org_name="Co")
    items = _collect_inbox(tmp_path)
    assert any(i.get("category") == "company_setup" for i in items)

    await cmd_inbox_list(argparse.Namespace(kind=None, category="company_setup", min_impact=None))
    assert "承認して" in capsys.readouterr().out

    await cmd_inbox_list(argparse.Namespace(kind=None, category="nonexistent", min_impact=None))
    assert "一致する項目がありません" in capsys.readouterr().out

    # human_task は revenue_impact=1 なので --min-impact 2 で除外される
    await cmd_inbox_list(argparse.Namespace(kind=None, category=None, min_impact=2))
    assert "承認して" not in capsys.readouterr().out
