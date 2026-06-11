"""ContentJob ストア / runner / scheduler のテスト（投稿生成・人間承認・レート制限自動停止）。"""

from __future__ import annotations

import asyncio

from core.content.content_jobs import ContentJob, ContentJobStore
from core.content.content_runner import run_content_job
from core.content.content_scheduler import ContentScheduler
from core.org_factory import create_default_organization
from core.platform.state import PlatformStateManager


def _run(coro):
    return asyncio.run(coro)


def _setup_org(tmp_path, name="SNS Growth"):
    repo = tmp_path / "repo"
    repo.mkdir()
    psm = PlatformStateManager(platform_home=tmp_path / "home")
    org = create_default_organization(name, "content org", repo_path=str(repo))
    psm.save_organization(org)
    return psm, org


# ---- ContentJobStore ----


def test_store_add_list_get_delete(tmp_path):
    store = ContentJobStore(platform_home=tmp_path)
    job = store.add_job(ContentJob(org_name="SNS Growth", theme="朝の習慣", interval_seconds=3600))
    assert len(store.list_jobs()) == 1
    assert store.get_job(job.job_id).theme == "朝の習慣"
    assert store.set_enabled(job.job_id, False).enabled is False
    assert store.delete_job(job.job_id) is True
    assert store.list_jobs() == []


def test_due_and_mark_run_advances_next_run(tmp_path):
    store = ContentJobStore(platform_home=tmp_path)
    job = store.add_job(ContentJob(org_name="SNS Growth", interval_seconds=3600))
    # next_run_at 未設定 → 即 due
    assert [j.job_id for j in store.due_jobs()] == [job.job_id]
    store.mark_run(job.job_id, status="generated", detail="ok")
    # mark_run 後は next_run_at が未来 → due でない
    assert store.due_jobs() == []
    refreshed = store.get_job(job.job_id)
    assert refreshed.run_count == 1
    assert refreshed.last_status == "generated"


def test_disabled_job_not_due(tmp_path):
    store = ContentJobStore(platform_home=tmp_path)
    job = store.add_job(ContentJob(org_name="X", enabled=False))
    assert store.due_jobs() == []
    assert job.is_due() is False


# ---- run_content_job ----


def test_run_content_job_generates_pending_content_asset(tmp_path):
    """claude 不在でも投稿ドラフト（content_asset 提案・承認待ち）を repo に生成する。"""
    psm, org = _setup_org(tmp_path)
    job = ContentJob(org_name=org.name, kind="content_brief", theme="朝活のコツ")
    result = _run(run_content_job(job, psm))
    assert result["ok"] is True
    assert result["status"] == "generated"
    sm = psm.get_org_state_manager(org)
    proposals = sm.get_all_improvement_proposals()
    assert len(proposals) == 1
    assert proposals[0]["category"] == "content_asset"
    # 承認待ち（自動適用されない）
    from core.models.organization import is_active_improvement_proposal_status

    assert is_active_improvement_proposal_status(proposals[0].get("status"))


def test_run_content_job_stamps_publish_block_when_target_set(tmp_path):
    """投稿先が設定されたジョブの生成物には intervention_spec.publish が載る。"""
    psm, org = _setup_org(tmp_path)
    job = ContentJob(
        org_name=org.name,
        kind="content_brief",
        theme="朝活",
        publish_platform="note",
        publish_mode="auto",
    )
    result = _run(run_content_job(job, psm))
    assert result["ok"] is True
    proposals = psm.get_org_state_manager(org).get_all_improvement_proposals()
    spec = proposals[0].get("intervention_spec") or {}
    assert spec.get("publish") == {"platform": "note", "mode": "auto"}


def test_run_content_job_no_publish_block_without_target(tmp_path):
    """投稿先未指定なら publish ブロックは載らない（従来どおり下書きのみ）。"""
    psm, org = _setup_org(tmp_path)
    job = ContentJob(org_name=org.name, kind="content_brief", theme="朝活")
    _run(run_content_job(job, psm))
    proposals = psm.get_org_state_manager(org).get_all_improvement_proposals()
    spec = proposals[0].get("intervention_spec") or {}
    assert "publish" not in spec


def test_run_content_job_ignores_unsupported_platform(tmp_path):
    """未対応プラットフォームは publish ブロックを載せない（誤投稿を防ぐ）。"""
    psm, org = _setup_org(tmp_path)
    job = ContentJob(org_name=org.name, theme="t", publish_platform="instagram")
    _run(run_content_job(job, psm))
    proposals = psm.get_org_state_manager(org).get_all_improvement_proposals()
    spec = proposals[0].get("intervention_spec") or {}
    assert "publish" not in spec


def test_run_content_job_missing_org(tmp_path):
    psm = PlatformStateManager(platform_home=tmp_path / "home")
    job = ContentJob(org_name="NoSuch")
    result = _run(run_content_job(job, psm))
    assert result["ok"] is False
    assert result["status"] == "org_not_found"


def test_run_content_job_detects_rate_limit_in_success_body(tmp_path, monkeypatch):
    """claude が returncode-0 で usage-limit を返しても（例外でなくても）レート制限を検知し、
    提案を生成せず status=rate_limited を返す。"""
    psm, org = _setup_org(tmp_path)
    job = ContentJob(org_name=org.name, theme="t")

    class _Resp:
        content = "Claude usage limit reached. try again in 3 hours."

    class _Provider:
        async def generate(self, **_kw):
            return _Resp()

    monkeypatch.setattr("core.runtime.claude_code.claude_available", lambda: True)
    monkeypatch.setattr("core.llm.get_llm_provider", lambda *a, **k: _Provider())

    result = _run(run_content_job(job, psm))
    assert result["status"] == "rate_limited"
    # レート制限テキストが提案として保存されていない
    assert psm.get_org_state_manager(org).get_all_improvement_proposals() == []


def test_store_skips_malformed_records_and_coerces_kind(tmp_path):
    import json

    store = ContentJobStore(platform_home=tmp_path)
    good = store.add_job(ContentJob(org_name="X", kind="content_brief"))
    # org_name 欠落の壊れたレコードを直接書き込む
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    raw.append({"job_id": "broken", "kind": "content_brief"})
    store.path.write_text(json.dumps(raw), encoding="utf-8")
    # list は壊れたレコードをスキップ（500 にしない）
    ids = [j.job_id for j in store.list_jobs()]
    assert good.job_id in ids and "broken" not in ids
    # 未知 kind は generic に寄せる（update も add と同様）
    good.kind = "totally-unknown"
    store.update_job(good)
    assert store.get_job(good.job_id).kind == "generic"


# ---- ContentScheduler ----


def test_scheduler_runs_due_jobs(tmp_path):
    psm, org = _setup_org(tmp_path)
    sched = ContentScheduler(platform_home=tmp_path / "home", run_pdca=False)
    sched._store.add_job(ContentJob(org_name=org.name, theme="t"))
    stop = _run(sched.run_cycle())
    assert stop is False
    # 提案が生成された
    assert len(psm.get_org_state_manager(org).get_all_improvement_proposals()) == 1


def test_scheduler_self_stops_on_rate_limit(tmp_path, monkeypatch):
    """レート制限検知でサイクルが True（ループ停止）を返す。"""
    psm, org = _setup_org(tmp_path)
    sched = ContentScheduler(platform_home=tmp_path / "home", run_pdca=False)
    sched._store.add_job(ContentJob(org_name=org.name, theme="t"))

    async def fake_run(job, _psm, **_kwargs):
        return {"ok": False, "status": "rate_limited", "detail": "limit", "retry_at": None}

    monkeypatch.setattr("core.content.content_scheduler.run_content_job", fake_run)
    stop = _run(sched.run_cycle())
    assert stop is True
    assert sched.status()["rate_limited"] is True
