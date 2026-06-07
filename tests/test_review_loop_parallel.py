"""Tests for the parallelised REVIEW_LOOP execution.

The reviewer's result is discarded (only the main agent's result is returned),
so the two headless ``claude`` calls are overlapped with ``asyncio.gather``.
These tests prove the overlap and that the returned value is unchanged.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from core.orchestration.pre_task_orchestrator import PreTaskOrchestrator


def _task():
    return SimpleNamespace(input={}, task_type="code_review", description="x")


def _factory(agents):
    return lambda aid: agents.get(aid)


async def test_review_loop_runs_main_and_reviewer_concurrently():
    reviewer_started = asyncio.Event()

    class MainAgent:
        async def run(self, task):
            # Main only completes once the reviewer has started — if execution
            # were serial (main fully, then reviewer) this would never resolve.
            await asyncio.wait_for(reviewer_started.wait(), timeout=2.0)
            return SimpleNamespace(success=True, output={"who": "main"})

    class ReviewAgent:
        async def run(self, task):
            reviewer_started.set()
            return SimpleNamespace(success=True, output={"who": "rev"})

    orch = PreTaskOrchestrator()
    analysis = SimpleNamespace(recommended_agent_ids=["main", "rev"])
    result = await orch._execute_review_loop(
        _task(), analysis, _factory({"main": MainAgent(), "rev": ReviewAgent()})
    )

    assert result.output["who"] == "main"  # returns the main agent's result
    assert reviewer_started.is_set()  # reviewer ran concurrently


async def test_review_loop_single_agent_returns_main():
    class MainAgent:
        async def run(self, task):
            return SimpleNamespace(success=True, output={"who": "main"})

    orch = PreTaskOrchestrator()
    analysis = SimpleNamespace(recommended_agent_ids=["main"])
    result = await orch._execute_review_loop(_task(), analysis, _factory({"main": MainAgent()}))
    assert result.output["who"] == "main"


async def test_review_loop_reviewer_failure_does_not_break_main():
    class MainAgent:
        async def run(self, task):
            return SimpleNamespace(success=True, output={"who": "main"})

    class BadReviewer:
        async def run(self, task):
            raise RuntimeError("reviewer boom")

    orch = PreTaskOrchestrator()
    analysis = SimpleNamespace(recommended_agent_ids=["main", "rev"])
    result = await orch._execute_review_loop(
        _task(), analysis, _factory({"main": MainAgent(), "rev": BadReviewer()})
    )
    assert result.output["who"] == "main"


async def test_review_loop_main_failure_surfaces():
    class BadMain:
        async def run(self, task):
            raise RuntimeError("main boom")

    class ReviewAgent:
        async def run(self, task):
            return SimpleNamespace(success=True, output={"who": "rev"})

    orch = PreTaskOrchestrator()
    analysis = SimpleNamespace(recommended_agent_ids=["main", "rev"])
    result = await orch._execute_review_loop(
        _task(), analysis, _factory({"main": BadMain(), "rev": ReviewAgent()})
    )
    assert result.success is False
