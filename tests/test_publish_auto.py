"""PUB-AUTO: 無人実送信の安全境界（auto→送信直前まで自動準備、最終送信は人手）。

既定（フラグ OFF）では auto ジョブは assisted へ降格し handed_off（人手が最終送信）になる。
フラグ ON かつアダプタが実 auto 送信対応のときのみ auto が素通りする。
"""

from __future__ import annotations

from core.humans.human_tasks import HumanTaskStore
from core.publishing.auto_gate import auto_send_enabled, set_auto_send_enabled
from core.publishing.base import PublishResult
from core.publishing.publish_jobs import PublishJob, PublishJobStore
from core.publishing.runner import run_publish_job


class _ModeCapture:
    """target.mode を記録するフェイクアダプタ。assisted は handed_off、auto は published を模す。"""

    def __init__(self, platform: str = "note", supports_auto_send: bool = False):
        self.platform = platform
        self.supports_auto_send = supports_auto_send
        self.seen_mode: str | None = None

    async def publish(self, content, target, *, dry_run: bool = False) -> PublishResult:
        self.seen_mode = target.mode
        if target.mode == "assisted":
            return PublishResult(
                ok=True, platform=self.platform, url="", mode="assisted", handed_off=True
            )
        return PublishResult(
            ok=True, platform=self.platform, url="https://x/posted", mode=target.mode
        )


def _auto_job(store: PublishJobStore) -> PublishJob:
    return store.add_job(
        PublishJob(org_name="Co", platform="note", title="t", body="b", mode="auto")
    )


# ------------------------------------------------------------------ #
# auto_gate
# ------------------------------------------------------------------ #


def test_auto_send_disabled_by_default(tmp_path):
    assert auto_send_enabled(tmp_path) is False


def test_auto_send_flag_roundtrip(tmp_path):
    set_auto_send_enabled(True, platform_home=tmp_path)
    assert auto_send_enabled(tmp_path) is True
    set_auto_send_enabled(False, platform_home=tmp_path)
    assert auto_send_enabled(tmp_path) is False


# ------------------------------------------------------------------ #
# run_publish_job の境界降格
# ------------------------------------------------------------------ #


async def test_auto_downgrades_to_assisted_when_flag_off(tmp_path, monkeypatch):
    """既定（OFF）: auto ジョブは assisted へ降格し handed_off＋公開確認タスクが積まれる。"""
    store = PublishJobStore(platform_home=tmp_path)
    job = _auto_job(store)
    capture = _ModeCapture()
    monkeypatch.setattr("core.publishing.runner.get_adapter", lambda p: capture)

    result = await run_publish_job(job, store=store, platform_home=tmp_path, dry_run=False)

    assert capture.seen_mode == "assisted"  # 実送信せず準備のみ
    assert result["handed_off"] is True
    assert store.get_job(job.job_id).status == "handed_off"
    tasks = [
        t
        for t in HumanTaskStore(platform_home=tmp_path).list_tasks()
        if t.kind == "publish_confirm"
    ]
    assert len(tasks) == 1  # 人手が最終送信するタスク


async def test_auto_downgrades_when_flag_on_but_adapter_unsupported(tmp_path, monkeypatch):
    """フラグ ON でもアダプタが実 auto 送信未対応なら降格（安全側）。"""
    set_auto_send_enabled(True, platform_home=tmp_path)
    store = PublishJobStore(platform_home=tmp_path)
    job = _auto_job(store)
    capture = _ModeCapture(supports_auto_send=False)
    monkeypatch.setattr("core.publishing.runner.get_adapter", lambda p: capture)

    await run_publish_job(job, store=store, platform_home=tmp_path, dry_run=False)
    assert capture.seen_mode == "assisted"
    assert store.get_job(job.job_id).status == "handed_off"


async def test_auto_passes_through_when_enabled_and_supported(tmp_path, monkeypatch):
    """フラグ ON かつアダプタが実 auto 送信対応なら auto が素通りし published になる。"""
    set_auto_send_enabled(True, platform_home=tmp_path)
    store = PublishJobStore(platform_home=tmp_path)
    job = _auto_job(store)
    capture = _ModeCapture(supports_auto_send=True)
    monkeypatch.setattr("core.publishing.runner.get_adapter", lambda p: capture)

    await run_publish_job(job, store=store, platform_home=tmp_path, dry_run=False)
    assert capture.seen_mode == "auto"  # 無人実送信が許可された経路
    assert store.get_job(job.job_id).status == "published"


def test_no_shipped_adapter_supports_auto_send():
    """現状アダプタは実 auto 送信未対応＝無人実送信は構造的に発火しない（安全の保証）。"""
    from core.publishing.adapters import get_adapter
    from core.publishing.base import SUPPORTED_PLATFORMS

    for platform in SUPPORTED_PLATFORMS:
        assert getattr(get_adapter(platform), "supports_auto_send", False) is False
