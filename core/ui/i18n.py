"""
I18n — 多言語対応基盤 (I-12)
PANTHEON_LANG環境変数で日本語/英語切り替え
"""

from __future__ import annotations

import os

TRANSLATIONS: dict[str, dict[str, str]] = {
    "ja": {
        "status_healthy": "健康",
        "status_critical": "危機的",
        "proposals_pending": "未承認の提案",
        "no_orgs": "組織が登録されていません",
        "run_analyze": "pantheon analyze を実行してください",
    },
    "en": {
        "status_healthy": "Healthy",
        "status_critical": "Critical",
        "proposals_pending": "Pending Proposals",
        "no_orgs": "No organizations registered",
        "run_analyze": "Run pantheon analyze",
    },
}


class I18n:
    """Tiny env-driven translation helper."""

    def __init__(self):
        pass

    def get_language(self) -> str:
        return os.environ.get("PANTHEON_LANG", "ja")

    def t(self, key: str, **kwargs) -> str:
        lang = self.get_language()
        text = TRANSLATIONS.get(lang, {}).get(key)
        if text is None:
            text = TRANSLATIONS.get("ja", {}).get(key, key)
        return text.format(**kwargs) if kwargs else text
