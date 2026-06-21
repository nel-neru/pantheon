"""YouTube 統計の取得とエピソードのランキング（フィードバックループの計測側）。

公式 Data API v3 ``videos.list?part=statistics`` で再生数/高評価/コメント数を取る（OAuth）。
これらは確実に取得できる実数。視聴維持率(retention)/CTR は YouTube Analytics Reporting API
（analytics スコープ）が必要な「次の層」で、ここでは**捏造せず**未対応として明示する。

正直性: 認証情報が無ければ送出、API 失敗は ok=False／例外を正直に返す。``transport`` 注入で
ロジックをテストできる（実ネットワーク不要）。ランキングは純粋関数（テスト可能）。
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.media.youtube_auth import get_access_token

_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


@dataclass
class VideoStats:
    video_id: str
    views: int = 0
    likes: int = 0
    comments: int = 0


@dataclass
class InsightsReport:
    ranked: List[Dict[str, Any]] = field(default_factory=list)  # 再生数降順のエピソード
    total_views: int = 0
    note: str = ""


class _UrllibStatsTransport:
    def fetch_token(self, form: Dict[str, str]) -> Dict[str, Any]:  # youtube_auth と同契約
        from core.media.youtube_auth import _UrllibTokenTransport

        return _UrllibTokenTransport().fetch_token(form)

    def get_json(self, url: str, headers: Dict[str, str]) -> Dict[str, Any]:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def fetch_video_stats(
    video_ids: List[str],
    *,
    platform_home: Optional[Path] = None,
    transport: Any = None,
) -> Dict[str, VideoStats]:
    """Data API videos.list で各動画の statistics を取得する（OAuth・偽数値なし）。

    認証情報が無ければ ``MediaProviderNotConfigured``。空 ID は空 dict。
    """
    ids = [v for v in (video_ids or []) if v]
    if not ids:
        return {}
    tr = transport or _UrllibStatsTransport()
    access = get_access_token(platform_home, transport=tr)
    out: Dict[str, VideoStats] = {}
    # Data API は1リクエスト最大50件。素直に50件刻みで分割する。
    for i in range(0, len(ids), 50):
        chunk = ids[i : i + 50]
        query = urllib.parse.urlencode({"part": "statistics", "id": ",".join(chunk)})
        resp = tr.get_json(f"{_VIDEOS_URL}?{query}", {"Authorization": f"Bearer {access}"})
        for item in resp.get("items") or []:
            vid = str(item.get("id") or "")
            stats = item.get("statistics") or {}
            out[vid] = VideoStats(
                video_id=vid,
                views=_coerce_int(stats.get("viewCount")),
                likes=_coerce_int(stats.get("likeCount")),
                comments=_coerce_int(stats.get("commentCount")),
            )
    return out


def rank_episodes(published: List[Dict[str, Any]], stats: Dict[str, VideoStats]) -> InsightsReport:
    """公開済みエピソード（{episode_no, video_id, logline?}）を再生数降順でランキングする（純粋）。

    統計の無い動画は views=0 として末尾へ。次サイクルで「伸びた型」を厚くする判断材料。
    """
    rows: List[Dict[str, Any]] = []
    total = 0
    for pub in published:
        vid = str(pub.get("video_id") or "")
        s = stats.get(vid)
        views = s.views if s else 0
        total += views
        rows.append(
            {
                "episode_no": pub.get("episode_no"),
                "video_id": vid,
                "url": pub.get("url", ""),
                "logline": pub.get("logline", ""),
                "views": views,
                "likes": s.likes if s else 0,
                "comments": s.comments if s else 0,
            }
        )
    rows.sort(key=lambda r: r["views"], reverse=True)
    return InsightsReport(
        ranked=rows,
        total_views=total,
        note="retention/CTR は YouTube Analytics Reporting API（analytics スコープ）が必要な次の層（未対応＝捏造しない）",
    )
