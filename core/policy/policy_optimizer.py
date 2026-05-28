"""
PolicyOptimizer — PolicyEngineルール自己最適化 (H-04)
承認/却下実績からpolicyルール改善を提案する
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class RuleOptimizationProposal:
    rule_id: str
    current_action: str
    proposed_action: str
    reason: str
    evidence_count: int


class PolicyOptimizer:
    def __init__(self):
        self._last_proposals: list[RuleOptimizationProposal] = []

    def analyze_rule_effectiveness(self, decisions: list[dict]) -> list[RuleOptimizationProposal]:
        proposals: list[RuleOptimizationProposal] = []
        categories: dict[str, list[str]] = defaultdict(list)
        for decision in decisions:
            category = str(decision.get("category") or "uncategorized")
            categories[category].append(str(decision.get("action") or "").upper())

        for category, actions in categories.items():
            reject_count = sum(action == "REJECT" for action in actions)
            auto_approve_count = sum(action == "AUTO_APPROVE" for action in actions)
            total = len(actions)

            if reject_count >= 3:
                proposals.append(
                    RuleOptimizationProposal(
                        rule_id=f"reject_rule_{category}",
                        current_action="implicit",
                        proposed_action="REJECT",
                        reason=f"Category '{category}' was rejected repeatedly; add an explicit reject rule.",
                        evidence_count=reject_count,
                    )
                )

            if total and auto_approve_count / total > 0.8:
                proposals.append(
                    RuleOptimizationProposal(
                        rule_id=f"auto_approve_{category}",
                        current_action="AUTO_APPROVE",
                        proposed_action="LOOSEN_THRESHOLDS",
                        reason=f"Category '{category}' is auto-approved {auto_approve_count}/{total} times; thresholds can be relaxed.",
                        evidence_count=auto_approve_count,
                    )
                )

        self._last_proposals = proposals
        return proposals

    def format_proposals(self, proposals: list[RuleOptimizationProposal]) -> str:
        if not proposals:
            return "No policy optimization proposals."
        return "\n".join(
            f"- {proposal.rule_id}: {proposal.current_action} -> {proposal.proposed_action} ({proposal.reason}, evidence={proposal.evidence_count})"
            for proposal in proposals
        )
