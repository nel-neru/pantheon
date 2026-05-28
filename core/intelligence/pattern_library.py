"""
PatternLibrary — 実装パターンライブラリ (L-11)
成功した自己実装のパターンを蓄積・再利用する
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.platform.state import get_platform_home


@dataclass
class CodePattern:
    pattern_id: str
    name: str
    description: str
    code_snippet: str
    tags: list[str]
    use_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PatternLibrary:
    """Persist and search successful implementation patterns."""

    def __init__(self, platform_home=None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.file_path = self.platform_home / "pattern_library.json"

    def save_pattern(self, name: str, code: str, tags: list[str], description: str = "") -> CodePattern:
        patterns = self._load_all()
        pattern = CodePattern(
            pattern_id=f"pattern:{uuid4().hex[:8]}",
            name=name,
            description=description,
            code_snippet=code,
            tags=list(tags),
        )
        patterns.append(pattern)
        self._save_all(patterns)
        return pattern

    def search_patterns(self, query: str) -> list[CodePattern]:
        terms = [term.lower() for term in query.split() if term.strip()]
        results = []
        for pattern in self._load_all():
            haystack = " ".join([pattern.name, pattern.description, " ".join(pattern.tags)]).lower()
            if not terms or any(term in haystack for term in terms):
                results.append(pattern)
        return sorted(results, key=lambda item: item.use_count, reverse=True)

    def get_pattern(self, pattern_id: str) -> CodePattern | None:
        for pattern in self._load_all():
            if pattern.pattern_id == pattern_id:
                return pattern
        return None

    def record_use(self, pattern_id: str) -> None:
        patterns = self._load_all()
        for pattern in patterns:
            if pattern.pattern_id == pattern_id:
                pattern.use_count += 1
                break
        self._save_all(patterns)

    def _load_all(self) -> list[CodePattern]:
        if not self.file_path.exists():
            return []
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return [CodePattern(**item) for item in data.get("patterns", [])]

    def _save_all(self, patterns: list[CodePattern]) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"patterns": [asdict(pattern) for pattern in patterns]}
        self.file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
