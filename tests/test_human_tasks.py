"""Human Member タスク管理（core.humans.human_tasks）と publishing 連携のテスト。"""

from __future__ import annotations

import pytest

from core.humans.human_tasks import HumanTaskStore, enqueue_human_task


def test_add_list_complete(tmp_path):
    store = HumanTaskStore(platform_home=tmp_path)
    t = store.add("アカウント作成", kind="account_setup", org_name="Note Sales")
    assert t.status == "open"
    assert store.list_tasks("open") and not store.list_tasks("done")

    done = store.complete(t.task_id)
    assert done is not None and done.status == "done" and done.done_at
    assert not store.list_tasks("open")
    assert len(store.list_tasks("done")) == 1


def test_complete_unknown_returns_none(tmp_path):
    store = HumanTaskStore(platform_home=tmp_path)
    assert store.complete("nope") is None


def test_dedupe_key_avoids_double_open(tmp_path):
    store = HumanTaskStore(platform_home=tmp_path)
    a = store.add("公開確認", dedupe_key="publish_confirm:job1")
    b = store.add("公開確認", dedupe_key="publish_confirm:job1")
    assert a.task_id == b.task_id
    assert len(store.list_tasks()) == 1


def test_enqueue_helper_is_safe(tmp_path):
    t = enqueue_human_task("test", platform_home=tmp_path, kind="general")
    assert t is not None
    assert HumanTaskStore(platform_home=tmp_path).list_tasks("open")


@pytest.mark.asyncio
async def test_handed_off_publish_enqueues_human_task(tmp_path):
    """publishing が handed_off になると公開確認の人間タスクが積まれる。"""
    from core.publishing.base import PublishResult
    from core.publishing.publish_jobs import PublishJob, PublishJobStore
    from core.publishing.runner import run_publish_job

    class _HandoffPublisher:
        platform = "note"

        async def publish(self, content, target, *, dry_run=False):
            return PublishResult(
                ok=True, platform="note", mode=target.mode, handed_off=True, detail="d"
            )

    store = PublishJobStore(platform_home=tmp_path)
    job = store.add_job(PublishJob(org_name="Note Sales", platform="note", title="記事", body="b"))

    import core.publishing.runner as runner

    orig = runner.get_adapter
    runner.get_adapter = lambda p: _HandoffPublisher()
    try:
        result = await run_publish_job(job, store=store, platform_home=tmp_path, dry_run=False)
    finally:
        runner.get_adapter = orig

    assert result["handed_off"] is True
    assert store.get_job(job.job_id).status == "handed_off"
    tasks = HumanTaskStore(platform_home=tmp_path).list_tasks("open")
    assert any(t.kind == "publish_confirm" and t.ref == job.job_id for t in tasks)
