from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from agents.base import AgentTask
from agents.improvement_executor_agent import ImprovementExecutorAgent
from core.models.organization import AgentSkill, SpecialistAgent


@pytest.fixture
def agent() -> ImprovementExecutorAgent:
    specialist = SpecialistAgent(
        name="Improvement Executor",
        skills=[AgentSkill.DEEP_RESEARCH, AgentSkill.TOOL_INTEGRATION],
    )
    return ImprovementExecutorAgent(specialist)


class DummyIndex:
    def __init__(self) -> None:
        self.add_calls: list[list[str]] = []
        self.commit_calls: list[str] = []

    def add(self, files: list[str]) -> None:
        self.add_calls.append(files)

    def commit(self, message: str) -> None:
        self.commit_calls.append(message)


class DummyGitOps:
    def __init__(self) -> None:
        self.checkout_calls: list[tuple[str, ...]] = []

    def checkout(self, *args: str) -> None:
        self.checkout_calls.append(args)


class DummyRepo:
    def __init__(self, path) -> None:
        self.path = path
        self.git = DummyGitOps()
        self.index = DummyIndex()


class DummyGitModule:
    def __init__(self) -> None:
        self.repos: list[DummyRepo] = []

    def Repo(self, path):
        repo = DummyRepo(path)
        self.repos.append(repo)
        return repo


def test_run_rejects_path_traversal(tmp_path, agent: ImprovementExecutorAgent):
    task = AgentTask(
        task_type="improvement_execution",
        description="Reject malicious file paths",
        input={
            "repo_path": str(tmp_path),
            "suggestion": {"file_path": "../escape.py", "title": "Block traversal"},
        },
    )

    result = asyncio.run(agent.run(task))

    assert result.success is False
    assert result.error == "Path traversal is not allowed in suggestion.file_path"



def test_apply_local_change_rejects_absolute_paths(tmp_path, monkeypatch, agent: ImprovementExecutorAgent):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    fake_git = DummyGitModule()
    monkeypatch.setitem(sys.modules, "git", SimpleNamespace(Repo=fake_git.Repo))

    with pytest.raises(ValueError, match="Absolute paths are not allowed"):
        agent._apply_local_change(
            repo_path,
            str(repo_path.parent / "escape.py"),
            "updated",
            "summary",
            {"title": "Unsafe change"},
        )



def test_apply_local_change_writes_only_inside_repo(tmp_path, monkeypatch, agent: ImprovementExecutorAgent):
    repo_path = tmp_path / "repo"
    target = repo_path / "nested" / "file.py"
    target.parent.mkdir(parents=True)
    target.write_text("before", encoding="utf-8")
    fake_git = DummyGitModule()
    monkeypatch.setitem(sys.modules, "git", SimpleNamespace(Repo=fake_git.Repo))

    result = agent._apply_local_change(
        repo_path,
        "nested/file.py",
        "after",
        "summary",
        {"title": "Safe change"},
    )

    assert target.read_text(encoding="utf-8") == "after"
    assert result["file_path"] == "nested/file.py"
    assert result["branch"].startswith("pantheon/improvement-safe-change-")
    assert fake_git.repos[0].git.checkout_calls[0][0] == "-b"
    assert fake_git.repos[0].index.add_calls == [["nested/file.py"]]
    assert fake_git.repos[0].index.commit_calls == ["refactor: Safe change"]
