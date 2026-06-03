"""Tests that the default LLM client is wired through the runtime entry points.

これらは「クライアントが渡されたら各コンポーネントに伝播し、渡されなければ
従来のスタブ/ヒューリスティック動作を維持する」契約を固定する。
"""

from __future__ import annotations

from core.goals.abstract_goal_pipeline import AbstractGoalPipeline


def test_goal_pipeline_forwards_llm_client_to_subagents():
    sentinel = object()
    pipeline = AbstractGoalPipeline(llm_client=sentinel)
    assert pipeline._llm_client is sentinel
    assert pipeline._parser._llm is sentinel
    assert pipeline._decomposer._llm is sentinel
    assert pipeline._verifier._llm is sentinel


def test_goal_pipeline_without_client_keeps_subagents_unconfigured():
    pipeline = AbstractGoalPipeline()
    assert pipeline._llm_client is None
    assert pipeline._parser._llm is None
    assert pipeline._decomposer._llm is None
    assert pipeline._verifier._llm is None


def test_code_review_agent_uses_injected_provider():
    from agents.code_review_agent import CodeReviewAgent
    from core.models.organization import AgentSkill, SpecialistAgent

    sentinel = object()
    specialist = SpecialistAgent(
        name="Reviewer",
        skills=[AgentSkill.DEEP_RESEARCH, AgentSkill.PERFORMANCE_ANALYSIS],
    )
    agent = CodeReviewAgent(specialist, llm_provider=sentinel)
    assert agent._llm_provider is sentinel


def test_code_review_agent_without_provider_defaults_to_none():
    from agents.code_review_agent import CodeReviewAgent
    from core.models.organization import AgentSkill, SpecialistAgent

    specialist = SpecialistAgent(
        name="Reviewer",
        skills=[AgentSkill.DEEP_RESEARCH, AgentSkill.PERFORMANCE_ANALYSIS],
    )
    agent = CodeReviewAgent(specialist)
    assert agent._llm_provider is None


def test_orchestrator_factory_forwards_client_to_pre_task_and_agent_factory():
    from agents.orchestrator_agent import OrchestratorAgent

    sentinel = object()
    agent = OrchestratorAgent.create(llm_client=sentinel)
    orchestrator = agent._get_orchestrator()
    assert orchestrator._llm is sentinel
    assert orchestrator._agent_factory._llm is sentinel


def test_invoke_based_agent_uses_client_instead_of_stub():
    """核心: `.invoke()` 系エージェントはクライアントが渡されれば実LLM経路を使い、
    渡されなければテンプレート（スタブ）にフォールバックする。これが
    「APIキーがあればスタブに落ちない」契約のミニ実証（ネットワーク非依存）。
    """
    from agents.tool_design_agent import ToolDesignAgent
    from core.intelligence.capability_gap_analyzer import CapabilityGap
    from core.llm import LLMClient
    from core.llm.base import LLMProvider, LLMResponse

    class _FakeProvider(LLMProvider):
        @property
        def provider_name(self) -> str:
            return "fake"

        def get_model_name(self, task_type: str = "default") -> str:
            return "fake-model"

        async def generate(self, messages, **kwargs):
            return LLMResponse(
                content=(
                    '{"class_name": "InjectedTool", "file_path": "core/intelligence/injected.py", '
                    '"method_signatures": ["def run(self)"], "description": "from-llm", '
                    '"integration_points": [], "required_imports": [], "estimated_lines": 12}'
                ),
                model="fake-model",
            )

        async def stream(self, messages, **kwargs):
            yield ""

    gap = CapabilityGap(
        gap_id="gap:wiring",
        pattern_key="pat",
        description="desc",
        suggested_type="tool",
        suggested_name="StubTool",
        rationale="why",
    )

    # クライアント無し → テンプレート（suggested_name を使う）
    stub_spec = ToolDesignAgent(llm_client=None).design(gap)
    assert stub_spec.class_name == "StubTool"

    # クライアント有り → 実LLM経路（LLM が返した JSON を使う）
    llm_spec = ToolDesignAgent(llm_client=LLMClient(_FakeProvider())).design(gap)
    assert llm_spec.class_name == "InjectedTool"
    assert llm_spec.description == "from-llm"
