"""
Phase 2 — 自己改善ループを本物に: PreTaskOrchestrator 経由のエージェント選定と、
実 quality_score / timing の OrchestrationPatternStore へのフィードバックを検証する。
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from agents.base import AgentResult, AgentTask
from core.intelligence.capability_registry import CapabilityRegistry
from core.models.organization import ImprovementProposal
from core.orchestration.orchestration_pattern_store import OrchestrationPatternStore
from core.orchestration.pre_task_orchestrator import (
    OrchestrationPattern,
    PreTaskOrchestrator,
    TaskAnalysis,
)
from core.org_factory import create_default_organization
from core.quality.self_improvement_loop import SelfImprovementLoop
from core.state.manager import RepoStateManager


class _FakeExecutorAgent:
    """claude を呼ばずに成功を返す改善実行エージェントのスタブ。"""

    def __init__(self):
        self.ran = False

    async def run(self, task):
        self.ran = True
        return AgentResult(success=True, output={"change_summary": "applied"})


class _FakeFactory:
    def __init__(self, agent):
        self._agent = agent
        self.requested: list[str] = []

    def create(self, capability_id):
        self.requested.append(capability_id)
        return self._agent


def test_loop_routes_through_orchestrator_not_agents0(tmp_path):
    # エージェントを持たない Organization でも orchestrator 経由で実行できる
    org = create_default_organization("LoopOrg", "self improve")
    org.divisions = []  # get_all_agents() が空 → 旧コードならスキップされていた
    sm = RepoStateManager(tmp_path, "LoopOrg")
    proposal = ImprovementProposal(
        review_id=uuid4(),
        title="fix something",
        description="d",
        priority="low",
        category="documentation",
        file_path="docs/x.md",
    )
    sm.save_improvement_proposal(proposal)

    store = OrchestrationPatternStore(platform_home=tmp_path)
    registry = CapabilityRegistry(platform_home=tmp_path)  # 未スキャン → fallback 経路
    orchestrator = PreTaskOrchestrator(capability_registry=registry, pattern_store=store)
    fake_agent = _FakeExecutorAgent()
    factory = _FakeFactory(fake_agent)

    loop = SelfImprovementLoop(org, sm, orchestrator=orchestrator, agent_factory=factory)
    asyncio.run(loop.assign_and_execute_improvements([proposal.model_dump()]))

    # orchestrator 経由でエージェントが選ばれ実行された
    assert fake_agent.ran is True
    assert factory.requested  # capability_id が要求された
    # 提案は done に更新
    stored = sm.get_pending_improvement_proposals(limit=10)
    assert stored == []  # done になり active から外れる

    # 実 quality / timing がパターンストアに記録された（再ロードで永続化確認）
    reloaded = OrchestrationPatternStore(platform_home=tmp_path)
    records = [r for r in reloaded._records if r.task_type == "improvement_execution"]
    assert records, "improvement_execution の PatternRecord が記録されていない"
    assert records[-1].quality_score == 8.0  # 成功ヒューリスティック
    assert records[-1].success is True


def test_record_execution_passes_quality_and_timing(tmp_path):
    store = OrchestrationPatternStore(platform_home=tmp_path)
    orchestrator = PreTaskOrchestrator(pattern_store=store)
    task = AgentTask(task_type="improvement_execution", description="d", input={})
    analysis = TaskAnalysis(
        task_type="improvement_execution",
        description="d",
        recommended_pattern=OrchestrationPattern.SEQUENTIAL_PIPELINE,
        recommended_agent_ids=["agent:improvement_executor"],
    )
    orchestrator._record_execution(
        task, analysis, AgentResult(success=True), quality_score=8.5, execution_time_ms=123
    )
    records = store._records
    assert records[-1].quality_score == 8.5
    assert records[-1].execution_time_ms == 123


def test_record_execution_records_capability_usage(tmp_path):
    registry = CapabilityRegistry(platform_home=tmp_path)
    used: list[str] = []
    registry.record_usage = lambda cid: used.append(cid)  # type: ignore[assignment]
    orchestrator = PreTaskOrchestrator(capability_registry=registry)
    task = AgentTask(task_type="improvement_execution", description="d", input={})
    analysis = TaskAnalysis(
        task_type="improvement_execution",
        description="d",
        recommended_pattern=OrchestrationPattern.SINGLE_AGENT,
        recommended_agent_ids=["agent:improvement_executor"],
    )
    orchestrator._record_execution(task, analysis, AgentResult(success=True))
    assert used == ["agent:improvement_executor"]
