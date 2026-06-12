"""note アダプタの実投稿（assisted ハンドオフ）のテスト — 実ブラウザは起動しない。

フェイク launcher/page を注入してフロー論理（接続チェック→エディタ流し込み→
ブラウザを開いたままハンドオフ）と、runner の handed_off 意味論
（published と区別・成果に数えない）を検証する。
"""

from __future__ import annotations

import json

import core.publishing.adapters.handoff as handoff_mod
from core.publishing.adapters.note import (
    NOTE_BODY_SELECTOR,
    NOTE_EDITOR_URL,
    NOTE_TITLE_SELECTOR,
    NotePublisher,
)
from core.publishing.base import PublishContent, PublishResult, PublishTarget
from core.publishing.publish_jobs import PublishJob, PublishJobStore
from core.publishing.runner import run_publish_job
from core.publishing.session import SessionStore


class _FakePage:
    def __init__(self) -> None:
        self.goto_urls: list[str] = []
        self.waited: list[str] = []
        self.filled: dict[str, str] = {}
        self.fill_error: Exception | None = None

    async def goto(self, url: str) -> None:
        self.goto_urls.append(url)

    async def wait_for_selector(self, selector: str, timeout: int | None = None) -> None:
        self.waited.append(selector)

    async def fill(self, selector: str, value: str) -> None:
        if self.fill_error is not None:
            raise self.fill_error
        self.filled[selector] = value


class _FakeContext:
    def __init__(self, page: _FakePage) -> None:
        self._page = page

    async def new_page(self) -> _FakePage:
        return self._page


class _FakeLauncher:
    def __init__(self, page: _FakePage) -> None:
        self._page = page
        self.closed = False

    async def launch(self) -> _FakeContext:
        return _FakeContext(self._page)

    async def close(self) -> None:
        self.closed = True


def _connected_store(tmp_path) -> SessionStore:
    store = SessionStore(platform_home=tmp_path)
    store.ensure_dir("note")
    store.state_path("note").write_text(json.dumps({"cookies": []}), encoding="utf-8")
    return store


def _target(mode: str = "assisted") -> PublishTarget:
    return PublishTarget(platform="note", mode=mode)


def _content() -> PublishContent:
    return PublishContent(title="見出し", body="本文")


async def test_auto_mode_is_not_implemented_yet(tmp_path):
    publisher = NotePublisher(session_store=_connected_store(tmp_path))
    result = await publisher._publish_live(_content(), _target(mode="auto"))
    assert result.ok is False
    assert "auto" in result.error and "未実装" in result.error


async def test_not_connected_fails_with_connect_hint(tmp_path):
    factory_calls: list[int] = []
    publisher = NotePublisher(
        session_store=SessionStore(platform_home=tmp_path),
        launcher_factory=lambda: factory_calls.append(1),
    )
    result = await publisher._publish_live(_content(), _target())
    assert result.ok is False
    assert "pantheon publish connect note" in result.error
    assert factory_calls == []  # 未接続ならブラウザを起動しない


async def test_assisted_fills_editor_and_hands_off_with_browser_open(tmp_path, monkeypatch):
    monkeypatch.setattr(handoff_mod, "_HANDOFF_KEEPALIVE", [])
    page = _FakePage()
    launcher = _FakeLauncher(page)
    publisher = NotePublisher(
        session_store=_connected_store(tmp_path), launcher_factory=lambda: launcher
    )

    result = await publisher._publish_live(_content(), _target())

    assert result.ok is True
    assert result.handed_off is True
    assert page.goto_urls == [NOTE_EDITOR_URL]
    assert page.waited == [NOTE_TITLE_SELECTOR]  # エディタ描画を待ってから流し込む
    assert page.filled[NOTE_TITLE_SELECTOR] == "見出し"
    assert page.filled[NOTE_BODY_SELECTOR] == "本文"
    # assisted の契約: 最終公開は人間 — ブラウザは閉じずに開いたまま引き渡す。
    assert launcher.closed is False
    assert handoff_mod._HANDOFF_KEEPALIVE == [launcher]


async def test_next_handoff_prunes_closed_browsers(tmp_path, monkeypatch):
    """人間が閉じ終わったハンドオフの残骸は、次のハンドオフ時に解放される。"""

    class _DeadLauncher(_FakeLauncher):
        def is_alive(self) -> bool:
            return False

    class _LiveLauncher(_FakeLauncher):
        def is_alive(self) -> bool:
            return True

    dead = _DeadLauncher(_FakePage())
    live = _LiveLauncher(_FakePage())
    monkeypatch.setattr(handoff_mod, "_HANDOFF_KEEPALIVE", [dead, live])
    new_launcher = _FakeLauncher(_FakePage())
    publisher = NotePublisher(
        session_store=_connected_store(tmp_path), launcher_factory=lambda: new_launcher
    )

    result = await publisher._publish_live(_content(), _target())

    assert result.ok is True
    assert dead.closed is True  # 死んだ残骸は close で駆動プロセスを解放
    assert live.closed is False  # 人間が使用中のブラウザには触れない
    assert handoff_mod._HANDOFF_KEEPALIVE == [live, new_launcher]


async def test_fill_failure_closes_browser_and_is_honest(tmp_path, monkeypatch):
    monkeypatch.setattr(handoff_mod, "_HANDOFF_KEEPALIVE", [])
    page = _FakePage()
    page.fill_error = RuntimeError("selector not found")
    launcher = _FakeLauncher(page)
    publisher = NotePublisher(
        session_store=_connected_store(tmp_path), launcher_factory=lambda: launcher
    )

    result = await publisher._publish_live(_content(), _target())

    assert result.ok is False
    assert result.handed_off is False
    assert "流し込みに失敗" in result.error
    assert launcher.closed is True  # 失敗時はハンドオフせず必ず後始末
    assert handoff_mod._HANDOFF_KEEPALIVE == []


async def test_runner_marks_handed_off_without_recording_outcome(tmp_path, monkeypatch):
    """handed_off は published と区別し、未公開のものを成果（posts）に数えない。"""

    class _HandoffPublisher:
        platform = "note"

        async def publish(self, content, target, *, dry_run=False) -> PublishResult:
            return PublishResult(
                ok=True, platform="note", mode=target.mode, handed_off=True, detail="d"
            )

    store = PublishJobStore(platform_home=tmp_path)
    job = store.add_job(PublishJob(org_name="Note Sales", platform="note", title="t", body="b"))
    monkeypatch.setattr("core.publishing.runner.get_adapter", lambda p: _HandoffPublisher())

    result = await run_publish_job(job, store=store, platform_home=tmp_path, dry_run=False)

    assert result["ok"] is True and result["handed_off"] is True
    assert store.get_job(job.job_id).status == "handed_off"

    from core.metrics.outcomes import OutcomeStore

    summary = OutcomeStore(platform_home=tmp_path).summary_for_org("Note Sales")
    assert summary.by_metric.get("posts", {}).get("sum") is None  # 成果は未記録

    log_lines = (tmp_path / "publish_log.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(log_lines[-1])["handed_off"] is True  # 監査ログには残る


def test_confirm_handed_off_publishes_and_records_outcome(tmp_path):
    """人間の公開確認で初めて published + 成果記録（handed_off 意味論の出口側）。"""
    from core.publishing.runner import confirm_handed_off

    store = PublishJobStore(platform_home=tmp_path)
    job = store.add_job(PublishJob(org_name="Note Sales", platform="note", title="t", body="b"))
    store.mark_status(job.job_id, status="handed_off")

    result = confirm_handed_off(
        job.job_id, store=store, platform_home=tmp_path, result_url="https://note.com/x/n/abc"
    )

    assert result["ok"] is True
    updated = store.get_job(job.job_id)
    assert updated.status == "published"
    assert updated.result_url.endswith("abc")

    from core.metrics.outcomes import OutcomeStore

    summary = OutcomeStore(platform_home=tmp_path).summary_for_org("Note Sales")
    assert summary.by_metric.get("posts", {}).get("sum") == 1  # 確認で初めて成果に数える

    log_lines = (tmp_path / "publish_log.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(log_lines[-1])["confirmed_by_human"] is True


def test_confirm_outcome_is_idempotent_even_without_status_gate(tmp_path):
    """成果記録自体がジョブ固有 source で冪等（status ゲートを素通りした並行系でも二重計上しない）。"""
    from core.metrics.outcomes import OutcomeStore

    store = OutcomeStore(platform_home=tmp_path)
    first = store.record(
        "o", "posts", 1, unit="count", source="publish-confirm:job1", dedupe_on_source=True
    )
    second = store.record(
        "o", "posts", 1, unit="count", source="publish-confirm:job1", dedupe_on_source=True
    )
    other = store.record(
        "o", "posts", 1, unit="count", source="publish-confirm:job2", dedupe_on_source=True
    )

    assert second.event_id == first.event_id  # 既存イベントが返る（追記なし）
    assert other.event_id != first.event_id  # 別ジョブは別イベント
    assert store.summary_for_org("o").by_metric["posts"]["sum"] == 2


def test_confirm_rejects_non_handed_off_and_unknown(tmp_path):
    """queued/published 等は確認できない（成果の二重記録を防ぐ）。不在 ID も正直に失敗。"""
    from core.metrics.outcomes import OutcomeStore
    from core.publishing.runner import confirm_handed_off

    store = PublishJobStore(platform_home=tmp_path)
    job = store.add_job(PublishJob(org_name="o", platform="note", title="t", body="b"))

    result = confirm_handed_off(job.job_id, store=store, platform_home=tmp_path)
    assert result["ok"] is False
    assert store.get_job(job.job_id).status == "queued"  # 変更されない

    assert confirm_handed_off("nonexistent", store=store, platform_home=tmp_path)["ok"] is False

    # 確認 → 再確認は拒否（published は handed_off ではない）= 成果は 1 回だけ
    store.mark_status(job.job_id, status="handed_off")
    assert confirm_handed_off(job.job_id, store=store, platform_home=tmp_path)["ok"] is True
    assert confirm_handed_off(job.job_id, store=store, platform_home=tmp_path)["ok"] is False
    summary = OutcomeStore(platform_home=tmp_path).summary_for_org("o")
    assert summary.by_metric.get("posts", {}).get("sum") == 1


async def test_handed_off_job_is_not_due_again(tmp_path, monkeypatch):
    """handed_off は人間待ちであり、自動実行経路（due_jobs）に二度と乗らない。"""
    store = PublishJobStore(platform_home=tmp_path)
    job = store.add_job(PublishJob(org_name="o", platform="note", title="t", body="b"))
    store.mark_status(job.job_id, status="handed_off")
    assert store.get_job(job.job_id).status == "handed_off"
    assert [j.job_id for j in store.due_jobs()] == []
