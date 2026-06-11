"""Unit tests for Sprint 2 self-extension components."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.base import AgentTask
from agents.self_code_writer import CodeOutput, SelfCodeWriter
from agents.tool_design_agent import ImplementationSpec, ToolDesignAgent
from core.intelligence.capability_gap_analyzer import CapabilityGap
from core.intelligence.self_extension_pipeline import SelfExtensionPipeline
from core.intelligence.self_integration_tester import (
    FullValidationResult,
    ImportTestResult,
    SelfIntegrationTester,
    TestRunResult,
    ValidationResult,
)
from core.models.organization import AgentSkill
from core.state.manager import RepoStateManager


@pytest.fixture
def agent_gap() -> CapabilityGap:
    return CapabilityGap(
        gap_id="gap:test:agent",
        pattern_key="code_review",
        description="レビュー手順の自動化が不足している",
        suggested_type="agent",
        suggested_name="AsyncReviewAgent",
        rationale="レビューコンテキスト収集を再利用し、繰り返しコストを削減する。",
        priority="high",
    )


@pytest.fixture
def tool_gap() -> CapabilityGap:
    return CapabilityGap(
        gap_id="gap:test:tool",
        pattern_key="dependency_analysis",
        description="依存関係の再計算が多すぎる",
        suggested_type="tool",
        suggested_name="DependencyGraphBuilder",
        rationale="依存グラフを再利用して分析速度を上げる。",
        priority="medium",
    )


class TestToolDesignAgent:
    def test_design_non_llm_returns_gap_named_spec(self, agent_gap: CapabilityGap):
        agent = ToolDesignAgent(llm_client=None)

        spec = agent.design(agent_gap)

        assert spec.class_name == agent_gap.suggested_name
        assert spec.gap_id == agent_gap.gap_id
        assert spec.file_path == "agents/async_review_agent.py"
        assert any("run" in signature for signature in spec.method_signatures)

    def test_default_specialist_uses_required_skills(self):
        agent = ToolDesignAgent(llm_client=None)

        assert agent.skills == [
            AgentSkill.STRATEGIC_PLANNING,
            AgentSkill.AGENT_WORKFLOW_DESIGN,
        ]

    def test_run_returns_spec_in_output(self, agent_gap: CapabilityGap):
        agent = ToolDesignAgent(llm_client=None)
        task = AgentTask(
            task_type="design_gap",
            description="Create a spec for a capability gap",
            input={"gap": agent_gap},
        )

        result = asyncio.run(agent.run(task))

        assert result.success is True
        assert result.output["spec"].class_name == agent_gap.suggested_name

    def test_tool_gap_targets_core_intelligence_path(self, tool_gap: CapabilityGap):
        agent = ToolDesignAgent(llm_client=None)

        spec = agent.design(tool_gap)

        assert spec.file_path == "core/intelligence/dependency_graph_builder.py"
        assert all("run" not in signature for signature in spec.method_signatures)
        assert "CapabilityRegistry.scan_and_register_all()" in spec.integration_points[1]


class TestSelfCodeWriter:
    def test_write_code_non_llm_generates_agent_scaffold(self, agent_gap: CapabilityGap):
        spec = ToolDesignAgent(llm_client=None).design(agent_gap)
        writer = SelfCodeWriter(llm_client=None)

        output = writer.write_code(spec)

        assert output.file_path == spec.file_path
        assert "from __future__ import annotations" in output.code_content
        assert "class AsyncReviewAgent(BaseAgent):" in output.code_content
        assert "async def run(self, task: AgentTask) -> AgentResult:" in output.code_content

    def test_write_code_non_llm_generates_utility_scaffold(self, tool_gap: CapabilityGap):
        spec = ToolDesignAgent(llm_client=None).design(tool_gap)
        writer = SelfCodeWriter(llm_client=None)

        output = writer.write_code(spec)

        assert output.file_path == spec.file_path
        assert "class DependencyGraphBuilder:" in output.code_content
        assert "def execute(self, target: str) -> dict[str, Any]:" in output.code_content
        assert "self.spec_id" in output.code_content

    def test_run_returns_code_output(self, agent_gap: CapabilityGap):
        spec = ToolDesignAgent(llm_client=None).design(agent_gap)
        writer = SelfCodeWriter(llm_client=None)
        task = AgentTask(
            task_type="write_code",
            description="Generate code from implementation spec",
            input={"spec": spec},
        )

        result = asyncio.run(writer.run(task))

        assert result.success is True
        assert result.output["code_output"].spec_id == spec.spec_id


class TestSelfIntegrationTester:
    def test_validate_syntax_accepts_valid_python(self):
        tester = SelfIntegrationTester()
        code_output = CodeOutput(
            output_id="code:valid",
            file_path="agents/valid_module.py",
            code_content="from __future__ import annotations\n\nVALUE = 1\n",
            is_new_file=True,
            spec_id="spec:valid",
        )

        result = tester.validate_syntax(code_output)

        assert result.is_valid is True
        assert result.errors == []

    def test_validate_syntax_rejects_invalid_python(self):
        tester = SelfIntegrationTester()
        code_output = CodeOutput(
            output_id="code:invalid",
            file_path="agents/invalid_module.py",
            code_content="def broken(:\n    pass\n",
            is_new_file=True,
            spec_id="spec:invalid",
        )

        result = tester.validate_syntax(code_output)

        assert result.is_valid is False
        assert "SyntaxError" in result.errors[0]

    def test_test_import_loads_generated_module(self, tmp_path: Path):
        tester = SelfIntegrationTester()
        code_output = CodeOutput(
            output_id="code:importable",
            file_path="core/intelligence/importable_module.py",
            code_content="from __future__ import annotations\n\nVALUE = 42\n",
            is_new_file=True,
            spec_id="spec:importable",
        )

        result = tester.test_import(code_output, tmp_path)

        assert result.can_import is True
        assert result.error_message == ""
        assert not (tmp_path / ".pantheon" / "self_validation").exists()

    def test_run_existing_tests_parses_success_output(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        tester = SelfIntegrationTester()

        def fake_run(*args, **kwargs):
            return SimpleNamespace(
                returncode=0, stdout="............ [100%]\n12 passed in 0.08s\n", stderr=""
            )

        monkeypatch.setattr("core.intelligence.self_integration_tester.subprocess.run", fake_run)

        result = tester.run_existing_tests(tmp_path)

        assert result.passed is True
        assert result.failed is False
        assert result.test_count == 12
        assert result.errors == []

    def test_run_existing_tests_parses_failure_output(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        tester = SelfIntegrationTester()

        def fake_run(*args, **kwargs):
            return SimpleNamespace(
                returncode=1,
                stdout="..F [100%]\n1 failed, 11 passed in 0.08s\n",
                stderr="AssertionError: boom",
            )

        monkeypatch.setattr("core.intelligence.self_integration_tester.subprocess.run", fake_run)

        result = tester.run_existing_tests(tmp_path)

        assert result.passed is False
        assert result.failed is True
        assert result.test_count == 12
        assert any("AssertionError" in line for line in result.errors)

    def test_run_full_validation_combines_component_results(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        tester = SelfIntegrationTester()
        code_output = CodeOutput(
            output_id="code:full",
            file_path="agents/full_validation.py",
            code_content="VALUE = 1\n",
            is_new_file=True,
            spec_id="spec:full",
        )

        monkeypatch.setattr(
            tester,
            "validate_syntax",
            lambda output: ValidationResult(is_valid=True, errors=[], warnings=[]),
        )
        monkeypatch.setattr(
            tester,
            "test_import",
            lambda output, root: ImportTestResult(can_import=True, error_message=""),
        )
        monkeypatch.setattr(
            tester,
            "run_existing_tests",
            lambda root: TestRunResult(
                passed=True,
                failed=False,
                errors=[],
                test_count=12,
                duration_seconds=0.1,
            ),
        )

        result = tester.run_full_validation(code_output, tmp_path)

        assert isinstance(result, FullValidationResult)
        assert result.overall_pass is True
        assert result.details["tests"]["test_count"] == 12


class TestSelfExtensionPipeline:
    def test_run_for_gap_creates_proposal(self, agent_gap: CapabilityGap, tmp_path: Path):
        state_manager = RepoStateManager(tmp_path, "TestOrg")
        pipeline = SelfExtensionPipeline(
            gap_analyzer=None,
            design_agent=ToolDesignAgent(llm_client=None),
            code_writer=SelfCodeWriter(llm_client=None),
            integration_tester=SelfIntegrationTester(),
            state_manager=state_manager,
        )

        result = asyncio.run(pipeline.run_for_gap(agent_gap))
        pending = pipeline.get_pending_proposals()

        assert result.success is True
        assert result.proposal_id
        assert result.validation is not None and result.validation.is_valid is True
        assert len(pending) == 1
        assert pending[0].category == "self_extension"
        assert pending[0].file_path == result.code_output.file_path

    def test_run_for_gap_returns_failure_on_invalid_generated_code(self, agent_gap: CapabilityGap):
        class BadWriter:
            def write_code(self, spec: ImplementationSpec) -> CodeOutput:
                return CodeOutput(
                    output_id="code:bad",
                    file_path=spec.file_path,
                    code_content="def broken(:\n    pass\n",
                    is_new_file=True,
                    spec_id=spec.spec_id,
                )

        pipeline = SelfExtensionPipeline(
            gap_analyzer=None,
            design_agent=ToolDesignAgent(llm_client=None),
            code_writer=BadWriter(),
            integration_tester=SelfIntegrationTester(),
            state_manager=None,
        )

        result = asyncio.run(pipeline.run_for_gap(agent_gap))

        assert result.success is False
        assert result.proposal_id == ""
        assert result.validation is not None and result.validation.is_valid is False

    def test_run_all_gaps_collects_all_results(
        self, agent_gap: CapabilityGap, tool_gap: CapabilityGap
    ):
        pipeline = SelfExtensionPipeline(
            gap_analyzer=None,
            design_agent=ToolDesignAgent(llm_client=None),
            code_writer=SelfCodeWriter(llm_client=None),
            integration_tester=SelfIntegrationTester(),
            state_manager=None,
        )

        results = asyncio.run(pipeline.run_all_gaps([agent_gap, tool_gap]))

        assert len(results) == 2
        assert [result.gap_id for result in results] == [agent_gap.gap_id, tool_gap.gap_id]
        assert all(result.success for result in results)
