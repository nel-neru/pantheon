"""
FailurePatternRegistry — 失敗パターン蓄積と回避 (B-07)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.platform.state import get_platform_home


@dataclass
class FailurePattern:
    pattern_id: str
    category: str
    file_pattern: str
    reason: str
    occurrence_count: int
    first_seen: str
    last_seen: str


class FailurePatternRegistry:
    def __init__(self, platform_home=None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.patterns_file = self.platform_home / "failure_patterns.json"
        self._patterns: dict[tuple[str, str], FailurePattern] = {}
        self.load()

    def record_failure(self, category: str, file_path: str = "", reason: str = "") -> None:
        file_pattern = self._to_file_pattern(file_path)
        key = (category, file_pattern)
        now = datetime.now(timezone.utc).isoformat()
        pattern = self._patterns.get(key)
        if pattern is None:
            pattern = FailurePattern(
                pattern_id=f"{category}:{file_pattern}",
                category=category,
                file_pattern=file_pattern,
                reason=reason,
                occurrence_count=1,
                first_seen=now,
                last_seen=now,
            )
        else:
            pattern.occurrence_count += 1
            pattern.last_seen = now
            if reason:
                pattern.reason = reason
        self._patterns[key] = pattern
        self.save()

    def should_suppress(self, category: str, file_path: str = "") -> bool:
        file_pattern = self._to_file_pattern(file_path)
        pattern = self._patterns.get((category, file_pattern))
        return bool(pattern and pattern.occurrence_count >= 3)

    def get_patterns(self, limit: int = 10) -> list[FailurePattern]:
        patterns = sorted(
            self._patterns.values(),
            key=lambda pattern: (-pattern.occurrence_count, pattern.last_seen),
            reverse=False,
        )
        return patterns[:limit]

    def save(self) -> None:
        payload = [asdict(pattern) for pattern in self._patterns.values()]
        self.patterns_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self) -> None:
        self._patterns = {}
        if not self.patterns_file.exists():
            return
        try:
            payload = json.loads(self.patterns_file.read_text(encoding="utf-8"))
        except Exception:
            return
        for raw in payload:
            try:
                pattern = FailurePattern(**raw)
            except TypeError:
                continue
            self._patterns[(pattern.category, pattern.file_pattern)] = pattern

    def _to_file_pattern(self, file_path: str) -> str:
        if not file_path:
            return "*"
        path = Path(file_path)
        if path.suffix:
            return f"*{path.suffix}"
        return path.name or str(path)
