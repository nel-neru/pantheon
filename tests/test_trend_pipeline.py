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
    assert first["failed"] == 0
    # 再実行しても同じトレンドは再変換されない（候補ゼロ → failed も 0）
    second = convert_trends(platform_home=home, min_score=7.0)
    assert second["content_jobs"] == 0
    assert second["failed"] == 0  # "新規ゼロ" は failed=0（失敗とは別物）


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

    # 1 回目: job 成功・proposal 失敗 → 揃わないので failed に計上される
    first = convert_trends(platform_home=home, min_score=7.0)
    assert first["content_jobs"] == 1
    assert first["proposals"] == 0
    assert first["failed"] == 1  # 部分失敗を母数として残す（無変換と区別）
    assert len(ContentJobStore(home).list_jobs()) == 1

    # 2 回目: job は出典 URL 既出で重複生成されない、proposal は今度は成功 → failed=0
    second = convert_trends(platform_home=home, min_score=7.0)
    assert second["content_jobs"] == 0  # 二重生成しない
    assert second["proposals"] == 1
    assert second["failed"] == 0  # 両アーティファクトが揃ったので失敗なし
    assert len(ContentJobStore(home).list_jobs()) == 1  # job は依然 1 件


def _always_raise(*_a, **_k):
    raise RuntimeError("injected failure")


def test_convert_reports_failed_when_both_artifacts_fail(tmp_path, monkeypatch):
    """job も proposal も失敗したトレンドは failed=1（content_jobs=0 の "無変換" と区別）。"""
    home, psm, org = _setup(tmp_path, monkeypatch)
    _seed_trends(home, [9.0])

    monkeypatch.setattr("core.content.content_jobs.ContentJobStore.add_job", _always_raise)
    monkeypatch.setattr(
        "core.state.manager.RepoStateManager.save_improvement_proposal", _always_raise
    )

    result = convert_trends(platform_home=home, min_score=7.0)
    assert result["content_jobs"] == 0
    assert result["proposals"] == 0
    assert result["failed"] == 1  # 全失敗が母数に現れる

    # 失敗は processed 化されないので、依然失敗し続ける限り再試行され failed に残る
    again = convert_trends(platform_home=home, min_score=7.0)
    assert again["failed"] == 1  # skip されず（processed 化されていない）再評価される


def test_cc_proposals_reports_failed_count(tmp_path, monkeypatch):
    """propose_claude_code_updates も提案保存失敗を failed として返す。"""
    home, psm, org = _setup(tmp_path, monkeypatch)
    store = TrendStore(platform_home=home)
    store.add(
        TrendItem(
            source="web",
            url="https://anthropic.com/news/y",
            title="CC update",
            summary="s",
            genre="claude_code",
            score=6.0,
        )
    )
    monkeypatch.setattr(
        "core.state.manager.RepoStateManager.save_improvement_proposal", _always_raise
    )
    result = propose_claude_code_updates(platform_home=home)
    assert result["proposals"] == 0
    assert result["failed"] == 1


def test_convert_dedup_by_hash_not_url_substring(tmp_path, monkeypatch):
    """URL が prefix 関係（/1 と /11）でも、別トレンドの job は誤って抑制されない。"""
    home, psm, org = _setup(tmp_path, monkeypatch)
    store = TrendStore(platform_home=home)
    store.add(TrendItem(source="web", url="https://ex.com/11", title="A", score=9.0, genre="ai"))
    store.add(TrendItem(source="web", url="https://ex.com/1", title="B", score=8.0, genre="ai"))

    result = convert_trends(platform_home=home, min_score=7.0)
    assert result["content_jobs"] == 2  # prefix 関係でも両方 job 化される

    # 再実行で二重生成しない
    again = convert_trends(platform_home=home, min_score=7.0)
    assert again["content_jobs"] == 0
    assert len(ContentJobStore(home).list_jobs()) == 2


def test_convert_long_title_preserves_dedup(tmp_path, monkeypatch):
    """超長タイトルでも source_trend_hash で dedup されるため二重生成しない。"""
    home, psm, org = _setup(tmp_path, monkeypatch)
    store = TrendStore(platform_home=home)
    store.add(
        TrendItem(source="web", url="https://ex.com/x", title="超長" * 400, score=9.0, genre="ai")
    )
    first = convert_trends(platform_home=home, min_score=7.0)
    assert first["content_jobs"] == 1
    second = convert_trends(platform_home=home, min_score=7.0)
    assert second["content_jobs"] == 0  # タイトルが長くても二重生成しない


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
    # 失敗母数キーが summary に必ず存在し、健全サイクルでは 0（無変換と全失敗の区別軸）
    assert summary["convert_failed"] == 0
    assert summary["cc_failed"] == 0


def test_trend_scheduler_surfaces_convert_failed(tmp_path, monkeypatch):
    """変換が失敗するとデーモン summary に convert_failed として現れる（黙殺しない）。"""
    from core.runtime.quota_governor import Verdict
    from core.trends.trend_scheduler import TrendScheduler

    home, psm, org = _setup(tmp_path, monkeypatch)
    _seed_trends(home, [9.0])

    sched = TrendScheduler(platform_home=home)
    monkeypatch.setattr(sched._governor, "allow", lambda prio, **kw: Verdict(True, False, "ok"))

    async def fake_collect(**kwargs):
        return {"collected": 0, "added": 0}

    monkeypatch.setattr("core.trends.runner.collect_and_store", fake_collect)
    # job/proposal 生成を両方失敗させる → 当該トレンドは convert_failed に計上される
    monkeypatch.setattr("core.content.content_jobs.ContentJobStore.add_job", _always_raise)
    monkeypatch.setattr(
        "core.state.manager.RepoStateManager.save_improvement_proposal", _always_raise
    )

    summary = _run(sched.run_cycle())
    assert summary["content_jobs"] == 0
    assert summary["proposals"] == 0
    assert summary["convert_failed"] == 1  # "新規ゼロ" ではなく失敗として観測される
