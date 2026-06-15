"""短尺動画の投稿カレンダー — 日付つき下書き（半年分）の値オブジェクトと永続ストア。

正準は ``~/.pantheon/shortvideo_calendar.json``（JSON）。投稿は人間が 1 日 1 本（``status`` で管理）。
CSV / Markdown エクスポータで人間が作業しやすい形に出力する（``content/shortvideo_affiliate/``）。
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PLATFORM_YOUTUBE_SHORTS = "youtube_shorts"

# フック型（ロードマップ §4）。generator がローテーションで割り当てる。
HOOK_TYPES = ("pain", "result", "vs", "howto", "mistake", "tier")
HOOK_LABELS = {
    "pain": "悩み提示",
    "result": "成果・数字",
    "vs": "比較",
    "howto": "手順",
    "mistake": "やりがちな失敗",
    "tier": "ランキング",
}

STATUS_DRAFT = "draft"
STATUS_POSTED = "posted"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ShortVideoPost:
    """1 日分のショート動画下書き。"""

    day_index: int = 0  # 1..N（投稿順）
    date: str = ""  # YYYY-MM-DD（投稿予定日）
    platform: str = PLATFORM_YOUTUBE_SHORTS
    program_name: str = ""  # 主役の AI ツール
    program_id: str = ""
    hook_type: str = "pain"
    title: str = ""  # YouTube タイトル
    hook: str = ""  # 0-3秒の掴み
    script: str = ""  # 30-45秒の台本（複数行可）
    onscreen_text: List[str] = field(default_factory=list)  # テロップ
    caption: str = ""  # 概要欄の価値訴求 1 行
    hashtags: List[str] = field(default_factory=list)
    cta: str = ""  # 口頭 CTA
    affiliate_url_slug: str = ""  # 計測用リンクのスラッグ（実URLは概要欄で差し込む）
    status: str = STATUS_DRAFT  # draft / posted
    post_id: str = ""
    created_at: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        self.day_index = int(self.day_index or 0)
        self.platform = str(self.platform) or PLATFORM_YOUTUBE_SHORTS
        self.hook_type = str(self.hook_type).strip().lower()
        if self.hook_type not in HOOK_TYPES:
            self.hook_type = "pain"
        if not isinstance(self.onscreen_text, list):
            self.onscreen_text = []
        self.onscreen_text = [
            str(t) for t in self.onscreen_text if isinstance(t, (str, int, float))
        ]
        if not isinstance(self.hashtags, list):
            self.hashtags = []
        self.hashtags = [str(t) for t in self.hashtags if isinstance(t, (str, int, float))]
        if self.status not in (STATUS_DRAFT, STATUS_POSTED):
            self.status = STATUS_DRAFT
        if not self.post_id:
            self.post_id = f"sv:{self.day_index:03d}"
        if not self.created_at:
            self.created_at = _now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ShortVideoPost":
        known = {f for f in cls.__dataclass_fields__}  # noqa: C416
        return cls(**{k: v for k, v in d.items() if k in known})


def schedule_dates(start: date, count: int) -> List[str]:
    """``start`` から ``count`` 日分の YYYY-MM-DD 文字列リストを返す（1 日 1 本）。"""
    return [(start + timedelta(days=i)).isoformat() for i in range(max(0, count))]


class ShortVideoCalendarStore:
    """投稿カレンダーの永続ストア（``~/.pantheon/shortvideo_calendar.json``）。"""

    def __init__(self, platform_home: Optional[Path] = None):
        if platform_home is None:
            from core.platform.state import get_platform_home

            platform_home = get_platform_home()
        self.platform_home = Path(platform_home)
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.path = self.platform_home / "shortvideo_calendar.json"

    def _load_raw(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return data if isinstance(data, list) else []

    def _save_raw(self, items: List[Dict[str, Any]]) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def list_posts(self) -> List[ShortVideoPost]:
        out: List[ShortVideoPost] = []
        for d in self._load_raw():
            if not isinstance(d, dict):
                continue
            try:
                out.append(ShortVideoPost.from_dict(d))
            except (TypeError, ValueError):
                continue
        out.sort(key=lambda p: p.day_index)
        return out

    def replace_all(self, posts: List[ShortVideoPost]) -> int:
        """カレンダー全体を置き換える（量産バッチの投入用）。件数を返す。"""
        self._save_raw([p.to_dict() for p in posts])
        return len(posts)

    def add_posts(self, posts: List[ShortVideoPost]) -> int:
        """day_index 一致は上書き、無ければ追加。投入件数を返す。"""
        items = self._load_raw()
        by_idx = {d.get("day_index"): i for i, d in enumerate(items) if isinstance(d, dict)}
        for p in posts:
            d = p.to_dict()
            if p.day_index in by_idx:
                items[by_idx[p.day_index]] = d
            else:
                by_idx[p.day_index] = len(items)
                items.append(d)
        self._save_raw(items)
        return len(posts)

    def get_by_day(self, day_index: int) -> Optional[ShortVideoPost]:
        for p in self.list_posts():
            if p.day_index == day_index:
                return p
        return None

    def get_by_date(self, day: str) -> Optional[ShortVideoPost]:
        for p in self.list_posts():
            if p.date == day:
                return p
        return None

    def upcoming(self, today: Optional[str] = None, limit: int = 7) -> List[ShortVideoPost]:
        today = today or date.today().isoformat()
        return [p for p in self.list_posts() if p.date >= today][: max(0, limit)]

    def next_unposted(self, today: Optional[str] = None) -> Optional[ShortVideoPost]:
        """投稿すべき次の 1 本。未投稿(draft)のうち日付が最も早いもの（積み残しを優先）。"""
        drafts = [p for p in self.list_posts() if p.status == STATUS_DRAFT]
        if not drafts:
            return None
        drafts.sort(key=lambda p: (p.date, p.day_index))
        return drafts[0]

    def mark_posted(self, post_id: str, *, when: Optional[str] = None) -> Optional[ShortVideoPost]:
        items = self._load_raw()
        updated: Optional[ShortVideoPost] = None
        for d in items:
            if isinstance(d, dict) and d.get("post_id") == post_id:
                d["status"] = STATUS_POSTED
                d["notes"] = (d.get("notes", "") + f" [posted:{when or _now_iso()}]").strip()
                updated = ShortVideoPost.from_dict(d)
                break
        if updated is not None:
            self._save_raw(items)
        return updated


# --------------------------------------------------------------------------- #
# エクスポータ（人間が作業しやすい形）                                          #
# --------------------------------------------------------------------------- #
def render_calendar_csv(posts: List[ShortVideoPost]) -> str:
    """投稿カレンダーを CSV 文字列にする（一覧・予約管理用）。"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "day",
            "date",
            "platform",
            "program",
            "hook_type",
            "title",
            "hook",
            "cta",
            "hashtags",
            "link_slug",
            "status",
        ]
    )
    for p in posts:
        writer.writerow(
            [
                p.day_index,
                p.date,
                p.platform,
                p.program_name,
                p.hook_type,
                p.title,
                p.hook,
                p.cta,
                " ".join(p.hashtags),
                p.affiliate_url_slug,
                p.status,
            ]
        )
    return buf.getvalue()


def render_calendar_markdown(posts: List[ShortVideoPost]) -> str:
    """投稿カレンダーを Markdown（月ごとに見出し・全台本）にする。"""
    lines: List[str] = ["# 投稿カレンダー（AIショート動画アフィリエイト）", ""]
    lines.append(f"全 {len(posts)} 本 / 1 日 1 本。各日の台本をそのまま撮影・投稿に使えます。")
    lines.append("")
    current_month = ""
    for p in posts:
        month = p.date[:7] if p.date else "（日付未設定）"
        if month != current_month:
            current_month = month
            lines.append(f"\n## {month}\n")
        lines.append(
            f"### Day {p.day_index} — {p.date} — {p.program_name}（{HOOK_LABELS.get(p.hook_type, p.hook_type)}）"
        )
        lines.append(f"- **タイトル**: {p.title}")
        lines.append(f"- **フック(0-3s)**: {p.hook}")
        if p.script:
            lines.append("- **台本**:")
            for ln in p.script.splitlines():
                lines.append(f"    {ln}")
        if p.onscreen_text:
            lines.append(f"- **テロップ**: {' / '.join(p.onscreen_text)}")
        lines.append(f"- **CTA**: {p.cta}")
        lines.append(f"- **概要欄**: {p.caption}")
        lines.append(f"- **ハッシュタグ**: {' '.join(p.hashtags)}")
        lines.append(
            f"- **リンクslug**: `{p.affiliate_url_slug}`（概要欄に計測付きアフィリリンクを差し込む）"
        )
        lines.append("")
    return "\n".join(lines)
