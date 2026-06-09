"""プラットフォーム別アダプタのレジストリ。

``get_adapter(platform)`` で対応する Publisher を返す。アダプタ追加（Instagram/Threads 等）は
``_REGISTRY`` に1行足すだけで済む設計。
"""

from __future__ import annotations

from typing import Dict

from core.publishing.adapters.note import NotePublisher
from core.publishing.adapters.wordpress import WordPressPublisher
from core.publishing.adapters.x import XPublisher
from core.publishing.base import (
    PLATFORM_NOTE,
    PLATFORM_WORDPRESS,
    PLATFORM_X,
    Publisher,
)

_REGISTRY: Dict[str, type] = {
    PLATFORM_NOTE: NotePublisher,
    PLATFORM_X: XPublisher,
    PLATFORM_WORDPRESS: WordPressPublisher,
}


def get_adapter(platform: str) -> Publisher:
    cls = _REGISTRY.get(platform)
    if cls is None:
        raise ValueError(f"未対応のプラットフォーム: {platform}")
    return cls()


__all__ = ["get_adapter", "NotePublisher", "XPublisher", "WordPressPublisher"]
