"""PublishJobStore のCRUD・スケジューリング・堅牢性テスト。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.publishing.publish_jobs import (
    PublishJob,
    PublishJobStore,
    enqueue_from_proposal,
)


def _iso(delta_hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=delta_hours)).isoformat()


def test_add_and_list_job(tmp_path):
    store = PublishJobStore(platform_home=tmp_path)
    job = store.add_job(PublishJob(org_name="Note Sales", platform="note", title="t", body="b"))
    assert store.get_job(job.job_id) is not None
    assert len(store.list_jobs()) == 1
    assert (tmp_path / "publish_jobs.json").exists()


def test_unsupported_platform_rejected(tmp_path):
    store = PublishJobStore(platform_home=tmp_path)
    with pytest.raises(ValueError):
        store.add_job(PublishJob(org_name="o", platform="instagram"))


def test_due_jobs_respects_schedule_and_status(tmp_path):
    store = PublishJobStore(platform_home=tmp_path)
    j_past = store.add_job(PublishJob(org_name="o", platform="note", scheduled_at=_iso(-1)))
    j_future = store.add_job(PublishJob(org_name="o", platform="x", scheduled_at=_iso(1)))
    j_none = store.add_job(PublishJob(org_name="o", platform="wordpress"))
    due_ids = {j.job_id for j in store.due_jobs()}
    assert j_past.job_id in due_ids
    assert j_none.job_id in due_ids  # 予約なし = 即時投稿可
    assert j_future.job_id not in due_ids


def test_is_due_coerces_naive_scheduled_at():
    # naive な scheduled_at（legacy/外部編集）は UTC とみなす。coerce せず TypeError を
    # catch→return True していた頃は、未来予約でも「即 due」となり予約時刻より早く
    # 公開された（外向き publish のフェイルオープン）。
    naive_future = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(tzinfo=None)
    job = PublishJob(org_name="o", platform="note", scheduled_at=naive_future.isoformat())
    assert job.is_due() is False  # 未来予約 → まだ公開しない

    naive_past = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(tzinfo=None)
    job_past = PublishJob(org_name="o", platform="note", scheduled_at=naive_past.isoformat())
    assert job_past.is_due() is True

    # 解析不能な値は従来どおり fallback（due スキャンを落とさない）。
    assert PublishJob(org_name="o", platform="note", scheduled_at="garbage").is_due() is True


def test_published_job_is_not_due(tmp_path):
    store = PublishJobStore(platform_home=tmp_path)
    job = store.add_job(PublishJob(org_name="o", platform="note"))
    store.mark_status(job.job_id, status="published", result_url="https://note.com/x")
    updated = store.get_job(job.job_id)
    assert updated.status == "published"
    assert updated.result_url == "https://note.com/x"
    assert job.job_id not in {j.job_id for j in store.due_jobs()}


def test_mark_status_failed_bumps_attempts(tmp_path):
    store = PublishJobStore(platform_home=tmp_path)
    job = store.add_job(PublishJob(org_name="o", platform="x"))
    store.mark_status(job.job_id, status="publishing", bump_attempts=True)
    store.mark_status(job.job_id, status="failed", error="boom")
    updated = store.get_job(job.job_id)
    assert updated.status == "failed"
    assert updated.error == "boom"
    assert updated.attempts == 1


def test_delete_job(tmp_path):
    store = PublishJobStore(platform_home=tmp_path)
    job = store.add_job(PublishJob(org_name="o", platform="note"))
    assert store.delete_job(job.job_id) is True
    assert store.get_job(job.job_id) is None
    assert store.delete_job("nope") is False


def test_corrupt_file_returns_empty(tmp_path):
    store = PublishJobStore(platform_home=tmp_path)
    store.path.write_text("{not valid json", encoding="utf-8")
    assert store.list_jobs() == []


def _content_asset_proposal(publish: dict | None) -> dict:
    spec = {"content": "本文です", "mode": "create"}
    if publish is not None:
        spec["publish"] = publish
    return {
        "id": "prop-123",
        "title": "朝活のコツ",
        "category": "content_asset",
        "file_path": "content/asagatsu.md",
        "intervention_spec": spec,
    }


def test_enqueue_from_proposal_creates_job(tmp_path):
    store = PublishJobStore(platform_home=tmp_path)
    proposal = _content_asset_proposal(
        {"platform": "note", "scheduled_at": _iso(2), "mode": "assisted", "account": "me"}
    )
    job = enqueue_from_proposal(proposal, "Note Sales", store=store)
    assert job is not None
    assert job.platform == "note"
    assert job.title == "朝活のコツ"
    assert job.body == "本文です"
    assert job.account == "me"
    assert job.source_proposal_id == "prop-123"
    assert job.file_path == "content/asagatsu.md"
    assert len(store.list_jobs()) == 1


def test_enqueue_from_proposal_without_publish_block_returns_none(tmp_path):
    store = PublishJobStore(platform_home=tmp_path)
    job = enqueue_from_proposal(_content_asset_proposal(None), "Note Sales", store=store)
    assert job is None
    assert store.list_jobs() == []


def test_enqueue_from_proposal_unsupported_platform_returns_none(tmp_path):
    store = PublishJobStore(platform_home=tmp_path)
    proposal = _content_asset_proposal({"platform": "instagram"})
    job = enqueue_from_proposal(proposal, "Note Sales", store=store)
    assert job is None
    assert store.list_jobs() == []
