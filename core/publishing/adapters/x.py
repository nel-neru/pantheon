"""X (Twitter) 投稿アダプタ。

無料での投稿はブラウザ自動操作が現実的（X API は有料枠）。280字を超える本文は将来
スレッド分割する。Phase 1 は assisted、Phase 2 で auto。``_publish_live`` が拡張点。
"""

from __future__ import annotations

from core.publishing.adapters.base import BrowserPublisher
from core.publishing.base import PLATFORM_X


class XPublisher(BrowserPublisher):
    platform = PLATFORM_X
