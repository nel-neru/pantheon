"""Tests for CoreImprovementAgent (agents/core_improvement_agent.py).

実 pytest を回さないよう、LLM と SafeChangeExecutor をフェイクで注入する。
"""

from __future__ import annotations

from pathlib import Path

from agents.base import AgentTask
from agents.core_improvement_agent import CoreImprovementAgent
from core.execution.safe_executor import ChangeResult


class FakeLLM:
    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self.calls: list[str] = []

    def generate_json(self, prompt: str) -> dict:
        self.calls.append(prompt)
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[idx]


class FakeExecutor:
    """apply_change を模倣: 成功なら new_content を書き込み、失敗なら据え置き。"""

    def __init__(self, project_root: Path, outcomes: list[bool]):
        self.project_root = Path(project_root)
        self._outcomes = list(outcomes)
        self.calls: list = []

    def apply_changes(self, changes: list) -> ChangeResult:
        idx = len(self.calls)
        self.calls.append(list(changes))
        success = self._outcomes[min(idx, len(self._outcomes) - 1)]
        primary = str(self.project_root / changes[0].file_path) if changes else ""
        if success:
            for change in changes:
                target = self.project_root / change.file_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(change.new_content, encoding="utf-8")
            return ChangeResult(
                success=True, file_path=primary, backup_path="",
                tests_passed=True, rolled_back=False,
            )
        return ChangeResult(
            success=False, file_path=primary, backup_path="",
            tests_passed=False, rolled_back=True,
            error_message="1 failed\nE   assert 1 == 2",
        )


def _make_target(tmp_path: Path) -> Path:
    target = tmp_path / "core" / "mod.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x = 1\n", encoding="utf-8")
    return target


def _task(**overrides) -> AgentTask:
    payload = {"instruction": "x を 2 にする", "file_path": "core/mod.py"}
    payload.update(overrides)
    return AgentTask(task_type="core_improvement", description="...", input=payload)


async def test_validate_only_reverts_working_tree(tmp_path):
    target = _make_target(tmp_path)
    llm = FakeLLM([{"modified_content": "x = 2\n", "change_summary": "bump x"}])
    agent = CoreImprovementAgent(
        llm_client=llm, project_root=tmp_path, executor=FakeExecutor(tmp_path, [True])
    )
    result = await agent.run(_task())

    assert result.success is True
    assert result.output["validated"] is True
    assert result.output["applied"] is False
    assert result.output["attempts"] == 1
    assert "x = 2" in result.output["modified_content"]
    assert "-x = 1" in result.output["diff"] and "+x = 2" in result.output["diff"]
    # 既定(validate_only)では作業ツリーは元に戻る
    assert target.read_text(encoding="utf-8") == "x = 1\n"


async def test_auto_apply_keeps_change(tmp_path):
    target = _make_target(tmp_path)
    llm = FakeLLM([{"modified_content": "x = 2\n", "change_summary": "bump"}])
    agent = CoreImprovementAgent(
        llm_client=llm, project_root=tmp_path, executor=FakeExecutor(tmp_path, [True])
    )
    result = await agent.run(_task(auto_apply=True))

    assert result.success is True
    assert result.output["applied"] is True
    assert target.read_text(encoding="utf-8") == "x = 2\n"


async def test_iterates_on_failure_then_succeeds(tmp_path):
    _make_target(tmp_path)
    llm = FakeLLM([
        {"modified_content": "x = bad\n", "change_summary": "try1"},
        {"modified_content": "x = 2\n", "change_summary": "try2"},
    ])
    agent = CoreImprovementAgent(
        llm_client=llm, project_root=tmp_path, executor=FakeExecutor(tmp_path, [False, True])
    )
    result = await agent.run(_task())

    assert result.success is True
    assert result.output["attempts"] == 2
    # 2回目のプロンプトに前回のテストエラーが渡る
    assert "失敗" in llm.calls[1] and "assert" in llm.calls[1]


async def test_exhausts_iterations_and_fails(tmp_path):
    _make_target(tmp_path)
    llm = FakeLLM([{"modified_content": "x = bad\n", "change_summary": "n"}])
    agent = CoreImprovementAgent(
        llm_client=llm, project_root=tmp_path, executor=FakeExecutor(tmp_path, [False, False])
    )
    result = await agent.run(_task(max_iterations=2))

    assert result.success is False
    assert result.output["attempts"] == 2
    assert result.output["last_error"]


async def test_requires_llm(tmp_path):
    _make_target(tmp_path)
    agent = CoreImprovementAgent(
        llm_client=None, project_root=tmp_path, executor=FakeExecutor(tmp_path, [True])
    )
    result = await agent.run(_task())
    assert result.success is False
    assert "LLM" in (result.error or "")


async def test_missing_file_fails(tmp_path):
    llm = FakeLLM([{"modified_content": "x = 2\n", "change_summary": "n"}])
    agent = CoreImprovementAgent(
        llm_client=llm, project_root=tmp_path, executor=FakeExecutor(tmp_path, [True])
    )
    result = await agent.run(_task(file_path="core/does_not_exist.py"))
    assert result.success is False


async def test_path_traversal_rejected(tmp_path):
    llm = FakeLLM([{"modified_content": "x\n", "change_summary": "n"}])
    agent = CoreImprovementAgent(
        llm_client=llm, project_root=tmp_path, executor=FakeExecutor(tmp_path, [True])
    )
    result = await agent.run(_task(file_path="../escape.py"))
    assert result.success is False


async def test_invalid_llm_output_fails(tmp_path):
    _make_target(tmp_path)
    llm = FakeLLM([{"change_summary": "missing modified_content"}])
    agent = CoreImprovementAgent(
        llm_client=llm, project_root=tmp_path, executor=FakeExecutor(tmp_path, [True])
    )
    result = await agent.run(_task())
    assert result.success is False


async def test_multi_file_change(tmp_path):
    a = tmp_path / "core" / "a.py"
    b = tmp_path / "core" / "b.py"
    a.parent.mkdir(parents=True, exist_ok=True)
    a.write_text("a = 1\n", encoding="utf-8")
    b.write_text("b = 1\n", encoding="utf-8")

    llm = FakeLLM([
        {"modified_content": "a = 2\n", "change_summary": "bump a"},
        {"modified_content": "b = 2\n", "change_summary": "bump b"},
    ])
    agent = CoreImprovementAgent(
        llm_client=llm, project_root=tmp_path, executor=FakeExecutor(tmp_path, [True])
    )
    result = await agent.run(
        AgentTask(
            task_type="core_improvement",
            description="...",
            input={"instruction": "両方を 2 に", "files": ["core/a.py", "core/b.py"]},
        )
    )

    assert result.success is True
    assert len(result.output["changes"]) == 2
    assert set(result.output["files"]) == {"core/a.py", "core/b.py"}
    # validate_only: 両ファイルとも元に戻る
    assert a.read_text(encoding="utf-8") == "a = 1\n"
    assert b.read_text(encoding="utf-8") == "b = 1\n"
