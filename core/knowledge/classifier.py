"""
KnowledgeClassifier — ナレッジ自動ドメイン分類 (B-05)
"""

from __future__ import annotations

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "security": ["セキュリティ", "認証", "vulnerability", "auth", "password", "injection"],
    "performance": ["パフォーマンス", "速度", "遅い", "最適化", "cache", "performance", "slow"],
    "maintainability": ["保守", "可読性", "重複", "リファクタ", "refactor", "readability"],
    "testing": ["テスト", "test", "coverage", "unittest", "pytest"],
    "architecture": ["アーキテクチャ", "設計", "architecture", "pattern", "structure"],
}


class KnowledgeClassifier:
    def classify(self, content: str, existing_tags: list[str] = None) -> list[str]:
        text = (content or "").lower()
        existing = set(existing_tags or [])
        detected: list[str] = []

        for domain, keywords in DOMAIN_KEYWORDS.items():
            if domain in existing:
                continue
            if any(keyword.lower() in text for keyword in keywords):
                detected.append(domain)
        return detected

    def auto_tag_entry(self, entry: dict) -> dict:
        updated = dict(entry)
        tags = list(updated.get("tags", []))
        detected = self.classify(updated.get("content", ""), existing_tags=tags)
        updated["tags"] = tags + detected
        return updated
