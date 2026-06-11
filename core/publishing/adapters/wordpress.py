"""アフィリエイト記事 CMS（WordPress 想定）投稿アダプタ。

WordPress は公式 REST API（Application Passwords）があるため、ブラウザ自動操作の代わりに
REST 連携も選べる（Phase 2）。公開先 CMS の実体（WordPress / Ghost / 静的サイト等）は
着手時に要確認＝それまでは ``_publish_live`` を拡張点として空けておく。
"""

from __future__ import annotations

from core.publishing.adapters.base import BrowserPublisher
from core.publishing.base import PLATFORM_WORDPRESS


class WordPressPublisher(BrowserPublisher):
    platform = PLATFORM_WORDPRESS
