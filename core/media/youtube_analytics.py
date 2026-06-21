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


@dataclass
class VideoAnalytics:
    video_id: str
    retention_pct: Optional[float] = None  # averageViewPercentage（視聴維持率）
    minutes_watched: Optional[float] = None
    ctr: Optional[float] = None  # impressionClickThroughRate（サムネCTR・取得不可なら None）


_ANALYTICS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"


def _query_report(tr: Any, access: str, params: Dict[str, str]) -> Dict[str, Any]:
    query = urllib.parse.urlencode(params)
    return tr.get_json(f"{_ANALYTICS_URL}?{query}", {"Authorization": f"Bearer {access}"})


def _rows_by_video(resp: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Analytics レポート（columnHeaders + rows）を {video_id: {metric: value}} へ。"""
    headers = [str(h.get("name")) for h in (resp.get("columnHeaders") or [])]
    if "video" not in headers:
        return {}
    vi = headers.index("video")
    out: Dict[str, Dict[str, Any]] = {}
    for row in resp.get("rows") or []:
        if len(row) != len(headers):
            continue
        out[str(row[vi])] = {headers[i]: row[i] for i in range(len(headers)) if i != vi}
    return out


def _as_float(value: Any) -> Optional[float]:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def fetch_video_analytics(
    video_ids: List[str],
    *,
    start_date: str,
    end_date: str,
    platform_home: Optional[Path] = None,
    transport: Any = None,
) -> Dict[str, VideoAnalytics]:
    """YouTube Analytics Reporting API で動画別の視聴維持率/視聴分/CTR を取得する（OAuth）。

    retention(averageViewPercentage) と estimatedMinutesWatched は信頼度の高い基本指標として
    1リクエストで取得。CTR(impressionClickThroughRate) はアカウント/権限で取れないことがあるため
    **別リクエストの best-effort**（失敗しても retention は返す＝部分成功を正直に・捏造しない）。
    認証情報が無ければ送出。analytics スコープが無いと API がエラー＝呼び出し側が正直に扱う。
    """
    ids = [v for v in (video_ids or []) if v]
    if not ids:
        return {}
    tr = transport or _UrllibStatsTransport()
    access = get_access_token(platform_home, transport=tr)
    common = {
        "ids": "channel==MINE",
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": "video",
        "filters": "video==" + ",".join(ids),
        "maxResults": "200",
    }
    core = _rows_by_video(
        _query_report(
            tr, access, {**common, "metrics": "views,averageViewPercentage,estimatedMinutesWatched"}
        )
    )
    ctr_rows: Dict[str, Dict[str, Any]] = {}
    try:
        ctr_rows = _rows_by_video(
            _query_report(
                tr, access, {**common, "metrics": "impressions,impressionClickThroughRate"}
            )
        )
    except Exception:  # noqa: BLE001 — CTR 取得不可は致命でない（retention は返す）
        ctr_rows = {}

    out: Dict[str, VideoAnalytics] = {}
    for vid in set(core) | set(ctr_rows):
        out[vid] = VideoAnalytics(
            video_id=vid,
            retention_pct=_as_float(core.get(vid, {}).get("averageViewPercentage")),
            minutes_watched=_as_float(core.get(vid, {}).get("estimatedMinutesWatched")),
            ctr=_as_float(ctr_rows.get(vid, {}).get("impressionClickThroughRate")),
        )
    return out


def rank_episodes(
    published: List[Dict[str, Any]],
    stats: Dict[str, VideoStats],
    analytics: Optional[Dict[str, VideoAnalytics]] = None,
) -> InsightsReport:
    """公開済みエピソードをランキングする（純粋）。analytics があれば retention 降順、無ければ再生数降順。

    統計/分析の無い動画は 0 として末尾へ。次サイクルで「伸びた型」を厚くする判断材料。
    """
    analytics = analytics or {}
    rows: List[Dict[str, Any]] = []
    total = 0
    has_retention = False
    for pub in published:
        vid = str(pub.get("video_id") or "")
        s = stats.get(vid)
        a = analytics.get(vid)
        views = s.views if s else 0
        total += views
        if a and a.retention_pct is not None:
            has_retention = True
        rows.append(
            {
                "episode_no": pub.get("episode_no"),
                "video_id": vid,
                "url": pub.get("url", ""),
                "logline": pub.get("logline", ""),
                "views": views,
                "likes": s.likes if s else 0,
                "comments": s.comments if s else 0,
                "retention_pct": a.retention_pct if a else None,
                "ctr": a.ctr if a else None,
                "minutes_watched": a.minutes_watched if a else None,
            }
        )
    # 維持率が取れていれば retention 優先（離脱されない型を学ぶ）、無ければ再生数で。
    if has_retention:
        rows.sort(
            key=lambda r: r["retention_pct"] if r["retention_pct"] is not None else -1, reverse=True
        )
        note = "視聴維持率(averageViewPercentage)降順。CTR は取得できた動画のみ表示。"
    else:
        rows.sort(key=lambda r: r["views"], reverse=True)
        note = (
            "再生数降順（retention/CTR 未取得＝analytics スコープ未付与/データ無し。捏造しない）。"
        )
    return InsightsReport(ranked=rows, total_views=total, note=note)
