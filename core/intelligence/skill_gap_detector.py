"""
SkillGapDetector — 動的スキルギャップ検出 (A-08)
失敗提案の分析から必要スキルを推定し、スキル追加を提案する
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from core.models.organization import AgentSkill


@dataclass
class SkillGap:
    gap_id: str
    detected_skill_name: str
    reason: str
    evidence_count: int
    detected_at: str


class SkillGapDetector:
    # 失敗カテゴリ -> 推奨スキル。AgentSkill の *enum 値*（lowercase）でキー化し、
    # detected_skill_name / get_skill_recommendation が実在の AgentSkill トークンを
    # 返すようにする（以前は UPPERCASE の enum 名＋AgentSkill に存在しない "TESTING"）。
    FAILURE_SKILL_MAP: dict[str, str] = {
        "security": AgentSkill.TOOL_INTEGRATION.value,
        "performance": AgentSkill.PERFORMANCE_ANALYSIS.value,
        "testing": AgentSkill.CODEBASE_EXPLORATION.value,
        "architecture": AgentSkill.STRATEGIC_PLANNING.value,
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
            gaps.append(
                SkillGap(
                    gap_id=str(uuid4()),
                    detected_skill_name=skill_name,
                    reason=f"{category} カテゴリで {failure_count} 件の失敗が発生しました。",
                    evidence_count=failure_count,
                    detected_at=datetime.now(timezone.utc).isoformat(),
                )
            )
            self._reported_categories.add(category)
        return gaps

    def get_skill_recommendation(self, category: str) -> str | None:
        return self.FAILURE_SKILL_MAP.get(category)
