"""Stress tests for state management"""

from __future__ import annotations

from uuid import uuid4

from core.models.organization import ImprovementProposal
from core.state.sqlite_manager import SQLiteStateManager


def _proposal(idx: int) -> ImprovementProposal:
    return ImprovementProposal(
        review_id=uuid4(),
        title=f"Proposal {idx}",
        description="stress test",
        file_path=f"core/file_{idx}.py",
        category="style",
        priority="low",
    )


def test_save_1000_proposals_performance(tmp_path):
    manager = SQLiteStateManager(tmp_path / "state.db")
    proposals = [_proposal(i) for i in range(1000)]
    for proposal in proposals:
        assert manager.save_improvement_proposal(proposal) is True
    assert len(manager.get_pending_improvement_proposals(limit=1000)) == 1000


def test_retrieve_filtered_proposals_fast(tmp_path):
    manager = SQLiteStateManager(tmp_path / "state.db")
    for i in range(1000):
        manager.save_improvement_proposal(_proposal(i))
    proposals = manager.get_pending_improvement_proposals(limit=200)
    assert len(proposals) == 200
