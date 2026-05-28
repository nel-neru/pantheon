"""Concurrency safety tests"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from core.models.organization import ImprovementProposal
from core.state.sqlite_manager import SQLiteStateManager


def _proposal(idx: int) -> ImprovementProposal:
    return ImprovementProposal(
        review_id=uuid4(),
        title=f"Concurrent {idx}",
        description="test",
        file_path=f"core/{idx}.py",
    )


def test_concurrent_writes_no_corruption(tmp_path):
    manager = SQLiteStateManager(tmp_path / "state.db")

    def worker(batch: int):
        for i in range(20):
            manager.save_improvement_proposal(_proposal(batch * 100 + i))

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker, idx) for idx in range(5)]
        for future in futures:
            future.result()

    assert len(manager.get_pending_improvement_proposals(limit=200)) == 100


def test_concurrent_reads_no_error(tmp_path):
    manager = SQLiteStateManager(tmp_path / "state.db")
    for i in range(50):
        manager.save_improvement_proposal(_proposal(i))

    def reader():
        return len(manager.get_pending_improvement_proposals(limit=100))

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda _: reader(), range(5)))

    assert results == [50] * 5
