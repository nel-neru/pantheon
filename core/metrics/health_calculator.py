"""
HealthCalculator — リアルタイム健康スコア計算 (C-05)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from core.metrics.lifecycle import OrganizationLifecycle


@dataclass
class HealthSnapshot:
    org_name: str
    score: float
    pending_proposals: int
    accepted_ratio: float
    last_improvement: str
    calculated_at: str


class HealthCalculator:
    def calculate(self, org_name: str, proposals: list[dict], decisions: list[dict]) -> HealthSnapshot:
        pending_proposals = sum(1 for proposal in proposals if self._is_pending(proposal))
        accepted_count = sum(1 for decision in decisions if self._is_accepted(decision))
        total_decisions = len(decisions)
        accepted_ratio = accepted_count / max(1, total_decisions)
        last_improvement = self._get_last_decision_timestamp(decisions)
        recency_bonus = 10 if self._is_recent(last_improvement) else 0
        score = 50 + accepted_ratio * 30 - min(pending_proposals / 5, 20) + recency_bonus
        score = max(0.0, min(100.0, score))
        return HealthSnapshot(
            org_name=org_name,
            score=round(score, 1),
            pending_proposals=pending_proposals,
            accepted_ratio=accepted_ratio,
            last_improvement=last_improvement,
            calculated_at=datetime.now(timezone.utc).isoformat(),
        )

    def format_score(self, snapshot: HealthSnapshot) -> str:
        lifecycle = OrganizationLifecycle()
        stage = lifecycle.determine_stage(snapshot.score)
        filled = max(0, min(5, int(round(snapshot.score / 20))))
        bar = "●" * filled + "○" * (5 - filled)
        return f"{bar} {int(round(snapshot.score))}/100 ({stage.name})"

    def _is_pending(self, proposal: dict) -> bool:
        status = str(proposal.get("status", "pending")).lower()
        return status not in {"accepted", "approved", "done", "rejected", "failed"}

    def _is_accepted(self, decision: dict) -> bool:
        for key in ("status", "decision", "outcome", "result"):
            value = str(decision.get(key, "")).lower()
            if value in {"accepted", "approved", "accept"}:
                return True
        return False

    def _get_last_decision_timestamp(self, decisions: list[dict]) -> str:
        timestamps: list[str] = []
        for decision in decisions:
            for key in ("decided_at", "timestamp", "created_at", "updated_at", "last_improvement"):
                value = decision.get(key)
                if value:
                    timestamps.append(str(value))
                    break
        valid = []
        for timestamp in timestamps:
            try:
                valid.append((datetime.fromisoformat(timestamp), timestamp))
            except ValueError:
                continue
        if not valid:
            return ""
        valid.sort(key=lambda item: item[0])
        return valid[-1][1]

    def _is_recent(self, timestamp: str) -> bool:
        if not timestamp:
            return False
        try:
            value = datetime.fromisoformat(timestamp)
        except ValueError:
            return False
        return value >= datetime.now(timezone.utc) - timedelta(days=7)
