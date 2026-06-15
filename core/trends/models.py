"""TrendItem — one collected trend signal."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import urlsplit, urlunsplit


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_url(url: str) -> str:
    """重複排除用に URL を正規化する（scheme/host 小文字化、query/fragment 除去、末尾 / 除去）。"""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, "", ""))


@dataclass
class TrendItem:
    """収集した 1 件のトレンド信号。"""

    source: str  # "web" | "youtube" | "x"
    url: str
    title: str
    summary: str = ""
    topics: List[str] = field(default_factory=list)
    genre: str = ""  # ジャンル適合（ai / side_business / video_edit / game_dev / ...）
    score: float = 0.0
    raw_excerpt: str = ""
    collected_at: str = field(default_factory=_now_iso)
    hash: str = ""

    def compute_hash(self) -> str:
        """正規化 URL（無ければ source+title）から content hash を導出する。"""
        basis = normalize_url(self.url) or f"{self.source}:{self.title.strip().lower()}"
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]

    def ensure_hash(self) -> "TrendItem":
        if not self.hash:
            self.hash = self.compute_hash()
        return self

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self.ensure_hash())

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TrendItem":
        raw_topics = d.get("topics")
        topics = (
            [str(t) for t in raw_topics if isinstance(t, str)]
            if isinstance(raw_topics, (list, tuple))
            else []
        )
        try:
            score = float(d.get("score", 0.0) or 0.0)
        except (TypeError, ValueError):  # 非数値 score は 0.0 へ退避（記録全体を壊さない）
            score = 0.0
        return cls(
            source=str(d.get("source", "")),
            url=str(d.get("url", "")),
            title=str(d.get("title", "")),
            summary=str(d.get("summary", "")),
            topics=topics,
            genre=str(d.get("genre", "")),
            score=score,
            raw_excerpt=str(d.get("raw_excerpt", "")),
            collected_at=str(d.get("collected_at", "") or _now_iso()),
            hash=str(d.get("hash", "")),
        ).ensure_hash()
