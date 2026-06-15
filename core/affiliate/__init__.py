"""AI 短尺動画アフィリエイト収益化モジュール（Round 5）。

- ``programs``      : アフィリエイト商材レジストリ（AffiliateProgram + Store + config シード）
- ``short_video``   : 投稿カレンダー（ShortVideoPost + CalendarStore + エクスポータ）
- ``generator``     : 台本生成（claude 生成 / 決定的フォールバック）＋スケジュール設計

ロードマップ: ``docs/plans/shortvideo-affiliate-monetization-roadmap.md``。
状態は ``~/.pantheon`` 配下（既存 ContentJob/Outcome と同じ規約）。投稿は人間が 1 日 1 本。
"""

from __future__ import annotations

from core.affiliate.programs import AffiliateProgram, AffiliateProgramStore
from core.affiliate.short_video import (
    HOOK_TYPES,
    PLATFORM_YOUTUBE_SHORTS,
    ShortVideoCalendarStore,
    ShortVideoPost,
)

__all__ = [
    "AffiliateProgram",
    "AffiliateProgramStore",
    "ShortVideoPost",
    "ShortVideoCalendarStore",
    "HOOK_TYPES",
    "PLATFORM_YOUTUBE_SHORTS",
]
