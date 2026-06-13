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


# --------------------------------------------------------------------------- #
# _publish_live（assisted ブラウザ自動操作）の直接ユニットテスト                   #
# 実ブラウザは起動せず、launcher_factory にフェイクを注入してフロー論理を検証する。 #
# --------------------------------------------------------------------------- #


class _FakePage:
    def __init__(self):
        self.goto_url = None
        self.fills = []

    async def goto(self, url, **_kw):
        self.goto_url = url

    async def wait_for_selector(self, _selector, **_kw):
        return True

    async def fill(self, selector, value, **_kw):
        self.fills.append((selector, value))


class _FakeContext:
    def __init__(self, page):
        self._page = page

    async def new_page(self):
        return self._page


class _FakeLauncher:
    def __init__(self):
        self.page = _FakePage()
        self.launched = False
        self.closed = False

    async def launch(self):
        self.launched = True
        return _FakeContext(self.page)

    async def close(self):
        self.closed = True


class _FakeSessionStore:
    def __init__(self, connected: bool = True):
        self._connected = connected

    def is_connected(self, _platform):
        return self._connected

    def state_path(self, platform):
        from pathlib import Path

        return Path(f"/tmp/{platform}/state.json")


async def test_note_publish_live_fills_editor_and_hands_off():
    from core.publishing.adapters.note import NOTE_EDITOR_URL, NOTE_TITLE_SELECTOR, NotePublisher

    launcher = _FakeLauncher()
    pub = NotePublisher(session_store=_FakeSessionStore(True), launcher_factory=lambda: launcher)
    result = await pub._publish_live(
        PublishContent(title="タイトル", body="本文"), PublishTarget(platform="note")
    )
    assert result.ok is True and result.handed_off is True
    assert launcher.launched is True and launcher.closed is False  # 開いたままハンドオフ
    assert launcher.page.goto_url == NOTE_EDITOR_URL
    assert (NOTE_TITLE_SELECTOR, "タイトル") in launcher.page.fills


async def test_x_publish_live_prefills_intent_and_hands_off():
    from core.publishing.adapters.x import X_COMPOSE_INTENT_URL, XPublisher

    launcher = _FakeLauncher()
    pub = XPublisher(session_store=_FakeSessionStore(True), launcher_factory=lambda: launcher)
    result = await pub._publish_live(
        PublishContent(title="t", body="ポスト本文"), PublishTarget(platform="x")
    )
    assert result.ok is True and result.handed_off is True
    assert launcher.page.goto_url.startswith(X_COMPOSE_INTENT_URL)
    assert "text=" in launcher.page.goto_url


async def test_wordpress_publish_live_opens_editor_and_hands_off():
    from core.publishing.adapters.wordpress import WP_ADMIN_NEW_POST_PATH, WordPressPublisher

    launcher = _FakeLauncher()
    pub = WordPressPublisher(
        session_store=_FakeSessionStore(True), launcher_factory=lambda: launcher
    )
    result = await pub._publish_live(
        PublishContent(title="記事", body="本文"),
        PublishTarget(platform="wordpress", account="https://example.com/"),
    )
    assert result.ok is True and result.handed_off is True
    assert launcher.page.goto_url == f"https://example.com{WP_ADMIN_NEW_POST_PATH}"


async def test_wordpress_publish_live_requires_site_url():
    from core.publishing.adapters.wordpress import WordPressPublisher

    pub = WordPressPublisher(session_store=_FakeSessionStore(True), launcher_factory=_FakeLauncher)
    result = await pub._publish_live(
        PublishContent(title="t", body="b"), PublishTarget(platform="wordpress", account="")
    )
    assert result.ok is False
    assert "サイトURL" in result.error


async def test_publish_live_fails_when_not_connected():
    from core.publishing.adapters.note import NotePublisher

    pub = NotePublisher(session_store=_FakeSessionStore(connected=False))
    result = await pub._publish_live(
        PublishContent(title="t", body="b"), PublishTarget(platform="note")
    )
    assert result.ok is False
    assert "未接続" in result.error


async def test_publish_live_auto_mode_is_rejected_until_phase2():
    from core.publishing.adapters.wordpress import WordPressPublisher

    pub = WordPressPublisher(session_store=_FakeSessionStore(True))
    result = await pub._publish_live(
        PublishContent(title="t", body="b"),
        PublishTarget(platform="wordpress", account="https://example.com", mode="auto"),
    )
    assert result.ok is False
    assert "auto" in result.error
