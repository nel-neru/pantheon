"""Tests for WIRE-B: トレンド → 新規会社候補提案（承認ゲート）。"""

from __future__ import annotations

import asyncio

from core.org_factory import create_default_organization
from core.platform.state import PlatformStateManager
from core.trends.business_pipeline import scan_business_proposals
from core.trends.models import TrendItem
from core.trends.store import TrendStore


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


def test_scan_creates_new_business_proposals(tmp_path, monkeypatch):
    home, psm, org = _setup(tmp_path, monkeypatch)
    _seed_trends(home, [9.0, 8.0, 3.0])  # 2 件が min_score(7) 以上

    result = scan_business_proposals(platform_home=home, min_score=7.0)
    assert result["proposals"] == 2

    proposals = psm.get_org_state_manager(org).get_all_improvement_proposals()
    new_biz = [p for p in proposals if p["category"] == "new_business"]
    assert len(new_biz) == 2
    # 承認ゲート: 自動採用されない proposed 状態で起票される
    assert all(p["status"] == "proposed" for p in new_biz)
    assert all(p["target_kind"] == "org_structure" for p in new_biz)
    assert all(p["title"].startswith("[新規会社候補]") for p in new_biz)


def test_scan_is_idempotent(tmp_path, monkeypatch):
    home, psm, org = _setup(tmp_path, monkeypatch)
    _seed_trends(home, [9.0])

    first = scan_business_proposals(platform_home=home, min_score=7.0)
    assert first["proposals"] == 1
    second = scan_business_proposals(platform_home=home, min_score=7.0)
    assert second["proposals"] == 0  # 同じトレンドは二重起票されない


def test_scan_skips_below_threshold(tmp_path, monkeypatch):
    home, psm, org = _setup(tmp_path, monkeypatch)
    _seed_trends(home, [6.9])  # min_score 7.0 未満 → 提案化しない

    result = scan_business_proposals(platform_home=home, min_score=7.0)
    assert result["proposals"] == 0
    proposals = psm.get_org_state_manager(org).get_all_improvement_proposals()
    assert not [p for p in proposals if p["category"] == "new_business"]


def test_scan_respects_max_per_run(tmp_path, monkeypatch):
    home, psm, org = _setup(tmp_path, monkeypatch)
    _seed_trends(home, [9.0, 8.9, 8.8, 8.7, 8.6, 8.5])

    result = scan_business_proposals(platform_home=home, min_score=7.0, max_per_run=3)
    assert result["proposals"] == 3
    assert result["skipped"] == 3


def test_scan_no_org(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: home)
    PlatformStateManager(platform_home=home)
    _seed_trends(home, [9.0])
    result = scan_business_proposals(platform_home=home, min_score=7.0)
    assert result["reason"] == "no_org"


def test_scan_genre_derived_from_trend(tmp_path, monkeypatch):
    """提案 description に genre / 推奨事業部が含まれる（新会社設計が反映される）。"""
    home, psm, org = _setup(tmp_path, monkeypatch)
    store = TrendStore(platform_home=home)
    store.add(
        TrendItem(
            source="web",
            url="https://ex.com/v",
            title="YouTube ショート攻略",
            summary="動画配信のトレンド",
            genre="youtube",
            score=9.0,
        )
    )
    result = scan_business_proposals(platform_home=home, min_score=7.0)
    assert result["proposals"] == 1
    props = psm.get_org_state_manager(org).get_all_improvement_proposals()
    desc = next(p for p in props if p["category"] == "new_business")["description"]
    # 動画系ジャンルは制作部門を含む 3 部門構成が推奨される
    assert "content_production" in desc


def test_daemon_cycle_includes_business_proposals(tmp_path, monkeypatch):
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
    assert summary["business_proposals"] == 1
