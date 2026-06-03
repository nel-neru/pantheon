"""ImprovementExecutorAgent: 検証済み変更の直接適用（LLM再生成なし）とプロバイダー解決。"""

from __future__ import annotations

import pytest

from agents.base import AgentTask
from agents.improvement_executor_agent import ImprovementExecutorAgent
from core.models.organization import AgentSkill, SpecialistAgent


def _specialist() -> SpecialistAgent:
    return SpecialistAgent(
        name="Executor",
        skills=[AgentSkill.PROMPT_ENGINEERING, AgentSkill.TOOL_INTEGRATION],
    )


def test_resolve_provider_prefers_injected():
    sentinel = object()
    agent = ImprovementExecutorAgent(_specialist(), llm_provider=sentinel)
    assert agent._resolve_provider() is sentinel


async def test_apply_validated_changes_writes_files_on_branch(tmp_path):
    git = pytest.importorskip("git")

    repo = git.Repo.init(tmp_path)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")

    (tmp_path / "core").mkdir()
    target = tmp_path / "core" / "m.py"
    target.write_text("x = 1\n", encoding="utf-8")
    repo.index.add(["core/m.py"])
    repo.index.commit("init")

    agent = ImprovementExecutorAgent(_specialist())
    task = AgentTask(
        task_type="improvement_execution",
        description="apply validated",
        input={
            "repo_path": str(tmp_path),
            "suggestion": {
                "title": "検証済み変更",
                "change_summary": "x を 2 に",
                "validated_changes": [
                    {"file_path": "core/m.py", "new_content": "x = 2\n"},
                ],
            },
        },
    )

    result = await agent.run(task)

    assert result.success is True
    assert result.output["applied_validated"] is True
    assert result.output["branch"].startswith("repocorp/improvement-")
    assert result.output["files"] == ["core/m.py"]
    assert target.read_text(encoding="utf-8") == "x = 2\n"
    # ブランチが切られている
    assert repo.active_branch.name == result.output["branch"]


async def test_apply_validated_changes_rejects_path_escape(tmp_path):
    git = pytest.importorskip("git")
    repo = git.Repo.init(tmp_path)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
    (tmp_path / "seed.txt").write_text("x", encoding="utf-8")
    repo.index.add(["seed.txt"])
    repo.index.commit("init")

    agent = ImprovementExecutorAgent(_specialist())
    task = AgentTask(
        task_type="improvement_execution",
        description="apply",
        input={
            "repo_path": str(tmp_path),
            "suggestion": {
                "title": "bad",
                "validated_changes": [{"file_path": "../escape.py", "new_content": "x"}],
            },
        },
    )
    result = await agent.run(task)
    assert result.success is False
