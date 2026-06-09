"""note.com 投稿アダプタ。

note は公式の投稿 API が無いため **ブラウザ自動操作（Playwright）が前提**。Phase 1 では
「エディタを開いてタイトル/本文を流し込み、最終公開は人間（assisted）」、Phase 2 で予約公開の
完全自動化（auto）を実装する。``_publish_live`` がその拡張点。
"""

from __future__ import annotations

from core.publishing.adapters.base import BrowserPublisher
from core.publishing.base import PLATFORM_NOTE


class NotePublisher(BrowserPublisher):
    platform = PLATFORM_NOTE
