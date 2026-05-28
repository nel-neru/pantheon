"""
SkillGapDetector — 動的スキルギャップ検出 (A-08)
失敗提案の分析から必要スキルを推定し、スキル追加を提案する
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class SkillGap:
    gap_id: str
    detected_skill_name: str
    reason: str
    evidence_count: int
    detected_at: str


class SkillGapDetector:
    FAILURE_SKILL_MAP: dict[str, str] = {
        "security": "TOOL_INTEGRATION",
        "performance": "PERFORMANCE_ANALYSIS",
        "testing": "TESTING",
        "architecture": "STRATEGIC_PLANNING",
    }

    def __init__(self):
        self.failure_counter: dict[str, int] = defaultdict(int)
        self._reported_categories: set[str] = set()

    def record_failure(self, category: str, file_path: str = "") -> None:
        _ = file_path
        self.failure_counter[category] += 1

    def detect_gaps(self) -> list[SkillGap]:
        gaps: list[SkillGap] = []
        for category, failure_count in sorted(self.failure_counter.items()):
            skill_name = self.FAILURE_SKILL_MAP.get(category)
            if failure_count < 3 or not skill_name or category in self._reported_categories:
                continue
            gaps.append(SkillGap(
                gap_id=str(uuid4()),
                detected_skill_name=skill_name,
                reason=f"{category} カテゴリで {failure_count} 件の失敗が発生しました。",
                evidence_count=failure_count,
                detected_at=datetime.now(timezone.utc).isoformat(),
            ))
            self._reported_categories.add(category)
        return gaps

    def get_skill_recommendation(self, category: str) -> str | None:
        return self.FAILURE_SKILL_MAP.get(category)
