"""YouTube 統計取得・ランキング（core/media/youtube_analytics）と story insights の検証。

Data API videos.list をモックし、OAuth トークン取得→統計取得→ランキングのロジックを実ネット
ワーク無しで検証。認証情報が無ければ送出、retention/CTR は未対応として捏造しないことを固定。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.media.credentials import MediaProviderNotConfigured
from core.media.youtube_analytics import fetch_video_stats, rank_episodes
from core.orchestration.company_plugins import install_company_plugin
from core.platform.state import PlatformStateManager


def _write_creds(tmp_path):
    (tmp_path / "youtube_credentials.json").write_text(
        json.dumps({"client_id": "c", "client_secret": "s", "refresh_token": "r"}), encoding="utf-8"
    )


class _FakeStatsTransport:
    def __init__(self, stats_by_id):
        self.stats_by_id = stats_by_id

    def fetch_token(self, form):
        return {"access_token": "at-1"}

    def get_json(self, url, headers):
        assert headers["Authorization"] == "Bearer at-1"
        # id=... を読み、対応する statistics を返す
        items = []
        for vid, st in self.stats_by_id.items():
            if vid in url:
                items.append({"id": vid, "statistics": st})
        return {"items": items}


def test_fetch_video_stats_requires_credentials(tmp_path):
    with pytest.raises(MediaProviderNotConfigured):
        fetch_video_stats(["v1"], platform_home=tmp_path)


def test_fetch_video_stats_parses_statistics(tmp_path):
    _write_creds(tmp_path)
    tr = _FakeStatsTransport(
        {
            "v1": {"viewCount": "1500", "likeCount": "80", "commentCount": "12"},
            "v2": {"viewCount": "300", "likeCount": "5", "commentCount": "1"},
        }
    )
    stats = fetch_video_stats(["v1", "v2"], platform_home=tmp_path, transport=tr)
    assert stats["v1"].views == 1500 and stats["v1"].likes == 80
    assert stats["v2"].views == 300


def test_fetch_video_stats_empty_ids():
    assert fetch_video_stats([], platform_home=Path(".")) == {}


def test_rank_episodes_orders_by_views_and_is_honest_about_retention():
    from core.media.youtube_analytics import VideoStats

    published = [
        {"episode_no": 1, "video_id": "v1", "logline": "灯台"},
        {"episode_no": 2, "video_id": "v2", "logline": "迷子"},
        {"episode_no": 3, "video_id": "v3", "logline": "未取得"},  # 統計なし→0
    ]
    stats = {"v1": VideoStats("v1", views=300), "v2": VideoStats("v2", views=1500)}
    report = rank_episodes(published, stats)
    assert [r["episode_no"] for r in report.ranked] == [2, 1, 3]  # 再生数降順
    assert report.total_views == 1800
    assert "retention" in report.note.lower()  # 維持率は未対応＝捏造しない明示


def test_cli_insights_no_published(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    psm = PlatformStateManager(platform_home=tmp_path)
    org_name = install_company_plugin("illustration_story_youtube", psm=psm)["org_name"]

    from commands.story import cmd_story_insights

    asyncio.run(cmd_story_insights(SimpleNamespace(org=org_name), get_psm=lambda: psm))
    assert "公開済みの動画がありません" in capsys.readouterr().out


def test_cli_insights_ranks_published(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    _write_creds(tmp_path)
    psm = PlatformStateManager(platform_home=tmp_path)
    org_name = install_company_plugin("illustration_story_youtube", psm=psm)["org_name"]
    org = psm.load_organization_by_name(org_name)

    # 公開記録（published.json）を2話分置く
    for ep, vid in ((1, "v1"), (2, "v2")):
        d = Path(org.workspace_path) / "episodes" / f"ep-{ep:02d}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "published.json").write_text(
            json.dumps({"episode_no": ep, "video_id": vid, "logline": f"ep{ep}"}), encoding="utf-8"
        )

    # fetch_video_stats を注入差し替え（鍵/ネット不要）
    from core.media.youtube_analytics import VideoStats

    monkeypatch.setattr(
        "core.media.youtube_analytics.fetch_video_stats",
        lambda video_ids, *, platform_home=None, transport=None: {
            "v1": VideoStats("v1", views=120),
            "v2": VideoStats("v2", views=900),
        },
    )
    # analytics（維持率/CTR）は別APIなので未取得を模す（実ネットワークを呼ばせない）
    monkeypatch.setattr(
        "core.media.youtube_analytics.fetch_video_analytics",
        lambda video_ids, **kw: {},
    )

    from commands.story import cmd_story_insights

    asyncio.run(cmd_story_insights(SimpleNamespace(org=org_name, days=365), get_psm=lambda: psm))
    out = capsys.readouterr().out
    assert "インサイト" in out and "総再生 1,020" in out
    insights = json.loads((Path(org.workspace_path) / "insights.json").read_text(encoding="utf-8"))
    assert insights["ranked"][0]["episode_no"] == 2  # 維持率未取得→再生数トップが先頭


def test_fetch_video_analytics_parses_retention_and_ctr(tmp_path):
    from core.media.youtube_analytics import fetch_video_analytics

    _write_creds(tmp_path)

    class _FakeAnalyticsTransport:
        def fetch_token(self, form):
            return {"access_token": "at-1"}

        def get_json(self, url, headers):
            if "averageViewPercentage" in url:
                return {
                    "columnHeaders": [
                        {"name": "video"},
                        {"name": "views"},
                        {"name": "averageViewPercentage"},
                        {"name": "estimatedMinutesWatched"},
                    ],
                    "rows": [["v1", 900, 61.5, 120.0], ["v2", 300, 33.0, 20.0]],
                }
            # CTR レポート
            return {
                "columnHeaders": [
                    {"name": "video"},
                    {"name": "impressions"},
                    {"name": "impressionClickThroughRate"},
                ],
                "rows": [["v1", 5000, 7.2]],
            }

    a = fetch_video_analytics(
        ["v1", "v2"],
        start_date="2026-01-01",
        end_date="2026-06-21",
        platform_home=tmp_path,
        transport=_FakeAnalyticsTransport(),
    )
    assert a["v1"].retention_pct == 61.5 and a["v1"].ctr == 7.2
    assert (
        a["v2"].retention_pct == 33.0 and a["v2"].ctr is None
    )  # CTR は v2 に無い→None（捏造しない）


def test_fetch_video_analytics_ctr_failure_keeps_retention(tmp_path):
    """CTR レポートが落ちても retention は返す（部分成功・捏造しない）。"""
    from core.media.youtube_analytics import fetch_video_analytics

    _write_creds(tmp_path)

    class _CtrFailsTransport:
        def fetch_token(self, form):
            return {"access_token": "at-1"}

        def get_json(self, url, headers):
            if "averageViewPercentage" in url:
                return {
                    "columnHeaders": [{"name": "video"}, {"name": "averageViewPercentage"}],
                    "rows": [["v1", 55.0]],
                }
            raise RuntimeError("ctr report not available")

    a = fetch_video_analytics(
        ["v1"],
        start_date="2026-01-01",
        end_date="2026-06-21",
        platform_home=tmp_path,
        transport=_CtrFailsTransport(),
    )
    assert a["v1"].retention_pct == 55.0 and a["v1"].ctr is None


def test_rank_episodes_prefers_retention_when_available():
    from core.media.youtube_analytics import VideoAnalytics, VideoStats, rank_episodes

    published = [
        {"episode_no": 1, "video_id": "v1"},
        {"episode_no": 2, "video_id": "v2"},
    ]
    stats = {"v1": VideoStats("v1", views=2000), "v2": VideoStats("v2", views=300)}
    analytics = {
        "v1": VideoAnalytics("v1", retention_pct=20.0),
        "v2": VideoAnalytics("v2", retention_pct=70.0),
    }
    report = rank_episodes(published, stats, analytics)
    # 再生数は v1 が上だが、維持率が高い v2 を上位にする（離脱されない型を学ぶ）
    assert [r["episode_no"] for r in report.ranked] == [2, 1]
    assert "維持率" in report.note
