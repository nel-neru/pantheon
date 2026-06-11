"""Tests for trend→jobs conversion and the trend daemon (B-3)."""

from __future__ import annotations

import asyncio

from core.content.content_jobs import ContentJobStore
from core.org_factory import create_default_organization
from core.platform.state import PlatformStateManager
from core.trends.models import TrendItem
from core.trends.store import TrendStore
from core.trends.trend_to_jobs import convert_trends, propose_claude_code_updates


def _run(coro):
    return asyncio.run(coro)


def _setup(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: home)
    psm = PlatformStateManager(platform_home=home)
    repo = tmp_path / "repo"
    repo.mkdir()
    org = create_default_organization("Content Org", "content", repo_path=str(repo))
    psm.save_organization(org)
    return home, psm, org


def _seed_trends(home, scores):
    store = TrendStore(platform_home=home)
    for i, score in enumerate(scores):
        store.add(
            TrendItem(
                source="web",
                url=f"https://ex.com/{i}",
                title=f"Trend {i}",
                summary="summary",
                genre="ai",
                score=score,
            )
        )


def test_convert_creates_jobs_and_proposals(tmp_path, monkeypatch):
    home, psm, org = _setup(tmp_path, monkeypatch)
    _seed_trends(home, [9.0, 8.0, 3.0])  # 2 件が min_score(7) 以上

    result = convert_trends(platform_home=home, min_score=7.0)
    assert result["content_jobs"] == 2
    assert result["proposals"] == 2

    jobs = ContentJobStore(home).list_jobs()
    assert len(jobs) == 2
    assert all(j.enabled is False for j in jobs)  # 承認ゲート: 既定で無効

    proposals = psm.get_org_state_manager(org).get_all_improvement_proposals()
    assert len(proposals) == 2
    assert all(p["category"] == "new_business" for p in proposals)


def test_convert_is_idempotent(tmp_path, monkeypatch):
    home, psm, org = _setup(tmp_path, monkeypatch)
    _seed_trends(home, [9.0])

    first = convert_trends(platform_home=home, min_score=7.0)
    assert first["content_jobs"] == 1
    # 再実行しても同じトレンドは再変換されない
    second = convert_trends(platform_home=home, min_score=7.0)
    assert second["content_jobs"] == 0


def test_convert_partial_failure_no_duplicate_job(tmp_path, monkeypatch):
    """proposal 保存が失敗しても、再実行で ContentJob を二重生成しない（冪等性）。"""
    home, psm, org = _setup(tmp_path, monkeypatch)
    _seed_trends(home, [9.0])

    sm = psm.get_org_state_manager(org)
    real_save = sm.save_improvement_proposal
    calls = {"n": 0}

    def flaky_save(proposal):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("disk error on proposal")
        return real_save(proposal)

    # PlatformStateManager.get_org_state_manager は都度生成するため、save をパッチ
    monkeypatch.setattr(
        "core.state.manager.RepoStateManager.save_improvement_proposal",
        lambda self, proposal: flaky_save(proposal),
    )

    # 1 回目: job 成功・proposal 失敗
    first = convert_trends(platform_home=home, min_score=7.0)
    assert first["content_jobs"] == 1
    assert first["proposals"] == 0
    assert len(ContentJobStore(home).list_jobs()) == 1

    # 2 回目: job は出典 URL 既出で重複生成されない、proposal は今度は成功
    second = convert_trends(platform_home=home, min_score=7.0)
    assert second["content_jobs"] == 0  # 二重生成しない
    assert second["proposals"] == 1
    assert len(ContentJobStore(home).list_jobs()) == 1  # job は依然 1 件


def test_convert_respects_max_per_run(tmp_path, monkeypatch):
    home, psm, org = _setup(tmp_path, monkeypatch)
    _seed_trends(home, [9.0, 8.9, 8.8, 8.7, 8.6, 8.5])

    result = convert_trends(platform_home=home, min_score=7.0, max_per_run=3)
    assert result["content_jobs"] == 3
    assert result["skipped"] == 3


def test_convert_no_org(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: home)
    PlatformStateManager(platform_home=home)
    _seed_trends(home, [9.0])
    result = convert_trends(platform_home=home, min_score=7.0)
    assert result["reason"] == "no_org"


def test_cc_trend_proposals(tmp_path, monkeypatch):
    home, psm, org = _setup(tmp_path, monkeypatch)
    store = TrendStore(platform_home=home)
    store.add(
        TrendItem(
            source="web",
            url="https://anthropic.com/news/x",
            title="New Claude Code feature",
            summary="hooks v2",
            genre="claude_code",
            score=6.0,
        )
    )
    result = propose_claude_code_updates(platform_home=home)
    assert result["proposals"] == 1
    props = psm.get_org_state_manager(org).get_all_improvement_proposals()
    assert any(p["category"] == "claude_code_config" for p in props)


def test_trend_daemon_registered():
    from core.runtime.daemon_registry import KNOWN_DAEMONS, get_spec

    assert "trend" in KNOWN_DAEMONS
    assert get_spec("trend").pid_filename == "trend_daemon.pid"
    assert get_spec("trend").frozen_flag == "--trend-daemon-run"


def test_trend_scheduler_skips_on_quota(tmp_path, monkeypatch):
    from core.runtime.quota_governor import Verdict
    from core.trends.trend_scheduler import TrendScheduler

    home = tmp_path / "home"
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: home)
    sched = TrendScheduler(platform_home=home)
    monkeypatch.setattr(
        sched._governor, "allow", lambda prio, **kw: Verdict(False, False, "soft_limit")
    )

    summary = _run(sched.run_cycle())
    assert summary["skipped_by_quota"] is True


def test_trend_scheduler_runs_pipeline(tmp_path, monkeypatch):
    from core.runtime.quota_governor import Verdict
    from core.trends.trend_scheduler import TrendScheduler

    home, psm, org = _setup(tmp_path, monkeypatch)
    _seed_trends(home, [9.0])

    sched = TrendScheduler(platform_home=home)
    monkeypatch.setattr(sched._governor, "allow", lambda prio, **kw: Verdict(True, False, "ok"))

    async def fake_collect(**kwargs):
        return {"collected": 0, "added": 0}

    monkeypatch.setattr("core.trends.runner.collect_and_store", fake_collect)

    summary = _run(sched.run_cycle())
    # 既存の seed トレンドが変換される
    assert summary["content_jobs"] == 1
    assert summary["proposals"] == 1
