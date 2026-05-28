"""
CapabilityGapDetector — 繰り返し課題からDivision新設提案 (E-04)
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass
class DivisionProposal:
    proposal_id: str
    division_name: str
    reason: str
    evidence_count: int
    triggered_category: str


class CapabilityGapDetector:
    def __init__(self):
        self._issue_counts: dict[str, int] = {}
        self._proposals: list[DivisionProposal] = []
        self._proposed_categories: set[str] = set()

    def record_repeated_issue(self, category: str) -> None:
        self._issue_counts[category] = self._issue_counts.get(category, 0) + 1

    def check_for_new_division(self, threshold: int = 5) -> list[DivisionProposal]:
        proposals: list[DivisionProposal] = []
        for category, count in sorted(self._issue_counts.items()):
            if count < threshold or category in self._proposed_categories:
                continue
            proposal = DivisionProposal(
                proposal_id=f"division:{uuid4()}",
                division_name=f"{category.title()} Division",
                reason=f"{category} に関する課題が繰り返し発生しています",
                evidence_count=count,
                triggered_category=category,
            )
            self._proposals.append(proposal)
            self._proposed_categories.add(category)
            proposals.append(proposal)
        return proposals

    def get_proposal_count(self) -> int:
        return len(self._proposals)
