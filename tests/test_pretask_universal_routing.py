"""
Phase 3 — PreTaskOrchestrator の普遍化: 中央ルーティングが実際に機能し（registry 配線）、
再入ガードで無限再帰を防ぎ、パターン学習が蓄積することを検証する。
"""

from __future__ import annotations

import asyncio

import core.platform.state as platform_state
from agents.base import AgentResult, AgentTask
from core.orchestration.orchestration_pattern_store import OrchestrationPatternStore
from core.orchestration.pre_task_orchestrator import (
    OrchestrationPattern,
    PreTaskOrchestrator,
    TaskAnalysis,
    is_routing_active,
)


def test_orchestrator_agent_routes_and_succeeds_for_code_review(tmp_path, monkeypatch):
    # registry / pattern_store を tmp に隔離
    monkeypatch.setattr(platform_state, "get_platform_home", lambda: tmp_path)
    from agents.orchestrator_agent import OrchestratorAgent

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def f():\n    x = 1\n    return x\n", encoding="utf-8")

    task = AgentTask(
        task_type="code_review",
        description="review",
        input={"repo_path": str(repo), "max_files": 3},
    )
    result = asyncio.run(OrchestratorAgent.create().run(task))
    # registry 配線により「No main agent」ではなく実際にエージェントが選ばれ実行される
    assert result.success is True
    assert isinstance(result.output, dict)


def test_is_routing_active_guard_set_during_execute_and_cleared_after():
    seen = {}

    class _ProbeAgent:
        async def run(self, task):
            seen["during"] = is_routing_active()
            return AgentResult(success=True, output={})

    orchestrator = PreTaskOrchestrator()
    analysis = TaskAnalysis(
        task_type="default",
        description="d",
        recommended_pattern=OrchestrationPattern.SINGLE_AGENT,
        recommended_agent_ids=["agent:x"],
    )
    assert is_routing_active() is False
    asyncio.run(
        orchestrator.execute(
            AgentTask(task_type="default", description="d"),
            analysis,
            agent_factory=lambda _id: _ProbeAgent(),
        )
    )
    assert seen["during"] is True  # 実行中はガードが立つ
    assert is_routing_active() is False  # 実行後は解除される


def test_patterns_accumulate_across_runs(tmp_path):
    store = OrchestrationPatternStore(platform_home=tmp_path)
    orchestrator = PreTaskOrchestrator(pattern_store=store)
    analysis = TaskAnalysis(
        task_type="code_review",
        description="d",
        recommended_pattern=OrchestrationPattern.SINGLE_AGENT,
        recommended_agent_ids=["agent:code_reviewer"],
    )

    class _OkAgent:
        async def run(self, task):
            return AgentResult(success=True, output={})

    for _ in range(3):
        asyncio.run(
            orchestrator.execute(
                AgentTask(task_type="code_review", description="d"),
                analysis,
                agent_factory=lambda _id: _OkAgent(),
            )
        )

    reloaded = OrchestrationPatternStore(platform_home=tmp_path)
    records = [r for r in reloaded._records if r.task_type == "code_review"]
    assert len(records) >= 3  # 実行ごとに蓄積される
