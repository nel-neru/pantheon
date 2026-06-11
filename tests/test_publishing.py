"""投稿アダプタと runner のテスト（実ブラウザは起動しない）。

dry-run プレビューの happy path、ブラウザ未接続時の正直な失敗、モックアダプタでの
実投稿成功→成果記録＆監査ログ、を検証する。
"""

from __future__ import annotations

import pytest

from core.publishing.adapters import get_adapter
from core.publishing.base import (
    SUPPORTED_PLATFORMS,
    PublishContent,
    PublishResult,
    PublishTarget,
)
from core.publishing.publish_jobs import PublishJob, PublishJobStore
from core.publishing.runner import process_due_publish_jobs, run_publish_job


class _FakePublisher:
    def __init__(self, platform: str = "note", url: str = "https://note.com/x/n/abc"):
        self.platform = platform
        self._url = url

    async def publish(self, content, target, *, dry_run=False) -> PublishResult:
        return PublishResult(ok=True, platform=self.platform, url=self._url, mode=target.mode)


async def test_adapter_dry_run_preview_is_safe():
    for platform in SUPPORTED_PLATFORMS:
        adapter = get_adapter(platform)
        result = await adapter.publish(
            PublishContent(title="見出し", body="本文1行目\n2行目"),
            PublishTarget(platform=platform),
            dry_run=True,
        )
        assert result.ok is True
        assert result.dry_run is True
        assert result.platform == platform
        assert result.url == ""  # 外部に作用していない


def test_get_adapter_unknown_raises():
    with pytest.raises(ValueError):
        get_adapter("instagram")


async def test_live_publish_without_browser_fails_honestly(tmp_path, monkeypatch):
    monkeypatch.setenv("PANTHEON_NO_BROWSER", "1")
    store = PublishJobStore(platform_home=tmp_path)
    job = store.add_job(PublishJob(org_name="Note Sales", platform="note", title="t", body="b"))
    result = await run_publish_job(job, store=store, platform_home=tmp_path, dry_run=False)
    assert result["ok"] is False
    updated = store.get_job(job.job_id)
    assert updated.status == "failed"
    assert updated.attempts == 1


async def test_dry_run_does_not_change_job_status(tmp_path):
    store = PublishJobStore(platform_home=tmp_path)
    job = store.add_job(PublishJob(org_name="o", platform="x", title="t", body="b"))
    result = await run_publish_job(job, store=store, platform_home=tmp_path, dry_run=True)
    assert result["ok"] is True and result["dry_run"] is True
    assert store.get_job(job.job_id).status == "queued"  # 未変更


async def test_successful_live_publish_records_outcome_and_log(tmp_path, monkeypatch):
    store = PublishJobStore(platform_home=tmp_path)
    job = store.add_job(PublishJob(org_name="Note Sales", platform="note", title="t", body="b"))
    monkeypatch.setattr("core.publishing.runner.get_adapter", lambda p: _FakePublisher())

    result = await run_publish_job(job, store=store, platform_home=tmp_path, dry_run=False)
    assert result["ok"] is True
    assert result["url"].endswith("abc")

    updated = store.get_job(job.job_id)
    assert updated.status == "published"
    assert updated.result_url.endswith("abc")

    from core.metrics.outcomes import OutcomeStore

    summary = OutcomeStore(platform_home=tmp_path).summary_for_org("Note Sales")
    assert summary.by_metric.get("posts", {}).get("sum") == 1

    assert (tmp_path / "publish_log.jsonl").exists()


async def test_process_due_publish_jobs_runs_only_due(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    store = PublishJobStore(platform_home=tmp_path)
    store.add_job(
        PublishJob(org_name="o", platform="note", title="now", body="b", mode="auto")
    )  # due
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    store.add_job(
        PublishJob(
            org_name="o", platform="x", title="later", body="b", mode="auto", scheduled_at=future
        )
    )
    monkeypatch.setattr("core.publishing.runner.get_adapter", lambda p: _FakePublisher(platform=p))

    results = await process_due_publish_jobs(store, platform_home=tmp_path)
    assert len(results) == 1
    assert results[0]["ok"] is True


async def test_process_due_publish_jobs_never_runs_assisted(tmp_path, monkeypatch):
    """assisted は『最終送信は人間』が契約 — 自動実行経路から絶対に発火しない（回帰防止）。"""
    store = PublishJobStore(platform_home=tmp_path)
    store.add_job(
        PublishJob(org_name="o", platform="note", title="manual", body="b")
    )  # 既定 assisted・即 due
    store.add_job(PublishJob(org_name="o", platform="x", title="auto", body="b", mode="auto"))
    monkeypatch.setattr("core.publishing.runner.get_adapter", lambda p: _FakePublisher(platform=p))

    results = await process_due_publish_jobs(store, platform_home=tmp_path)

    assert len(results) == 1
    assert results[0]["platform"] == "x"  # auto モードのジョブだけが実行される
    statuses = {j.title: j.status for j in store.list_jobs()}
    assert statuses["manual"] == "queued"  # assisted は手つかずで人間待ちのまま
    assert statuses["auto"] == "published"


async def test_scheduler_auto_publishes_only_auto_mode_jobs(tmp_path, monkeypatch):
    """daemon は auto モードの予約投稿のみ自動実行し、assisted は人間待ちで残す。"""
    from core.content.content_scheduler import ContentScheduler

    store = PublishJobStore(platform_home=tmp_path)
    auto_job = store.add_job(
        PublishJob(org_name="o", platform="note", title="auto", body="b", mode="auto")
    )
    assisted_job = store.add_job(
        PublishJob(org_name="o", platform="x", title="assisted", body="b", mode="assisted")
    )
    monkeypatch.setattr("core.publishing.runner.get_adapter", lambda p: _FakePublisher(platform=p))

    scheduler = ContentScheduler(platform_home=tmp_path, run_pdca=False)
    await scheduler.run_cycle()

    assert store.get_job(auto_job.job_id).status == "published"
    assert store.get_job(assisted_job.job_id).status == "queued"
