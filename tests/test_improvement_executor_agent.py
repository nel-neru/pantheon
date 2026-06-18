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


def test_run_applies_verbatim_generated_code_for_new_file(
    tmp_path, monkeypatch, agent: ImprovementExecutorAgent
):
    """self-extension: generated_code があれば新規ファイルを LLM 再生成せず verbatim 適用する。"""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    fake_git = DummyGitModule()
    monkeypatch.setitem(sys.modules, "git", SimpleNamespace(Repo=fake_git.Repo))

    # verbatim 経路では LLM を一切呼ばないことを保証する（呼ばれたら fail）。
    async def _must_not_call(*args, **kwargs):
        raise AssertionError("LLM should not be called when generated_code is present")

    monkeypatch.setattr(agent, "_generate_code_change", _must_not_call)

    code = "from __future__ import annotations\n\nclass AsyncReviewAgent:\n    pass\n"
    task = AgentTask(
        task_type="improvement_execution",
        description="Apply self-extension generated code",
        input={
            "repo_path": str(repo_path),
            # 生成先は新規ファイル（従来経路なら 'Target file not found' で失敗していた）。
            "suggestion": {
                "file_path": "agents/async_review_agent.py",
                "title": "Self-extension: AsyncReviewAgent",
                "category": "self_extension",
                "generated_code": code,
            },
        },
    )

    result = asyncio.run(agent.run(task))

    assert result.success is True
    written = repo_path / "agents" / "async_review_agent.py"
    assert written.read_text(encoding="utf-8") == code
    assert result.output["file_path"] == "agents/async_review_agent.py"
    assert result.output["branch"].startswith("pantheon/improvement-")


def test_run_without_generated_code_still_requires_existing_file(
    tmp_path, agent: ImprovementExecutorAgent
):
    """回帰: generated_code が無ければ従来どおり新規ファイルは 'Target file not found' で失敗する。"""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    task = AgentTask(
        task_type="improvement_execution",
        description="No generated_code, nonexistent file",
        input={
            "repo_path": str(repo_path),
            "suggestion": {"file_path": "agents/missing.py", "title": "Improve"},
        },
    )

    result = asyncio.run(agent.run(task))

    assert result.success is False
    assert "Target file not found" in (result.error or "")


def test_apply_local_change_rejects_absolute_paths(
    tmp_path, monkeypatch, agent: ImprovementExecutorAgent
):
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


def test_apply_local_change_writes_only_inside_repo(
    tmp_path, monkeypatch, agent: ImprovementExecutorAgent
):
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


def test_apply_local_change_japanese_title_yields_valid_branch(
    tmp_path, monkeypatch, agent: ImprovementExecutorAgent
):
    """日本語タイトル（提案の主言語）でもローカルブランチ名が有効・非退化になる。

    旧実装は slug が '-' に潰れ pantheon/improvement---<ts> という区別不能なブランチを作っていた
    （PR 経路と同一バグ。ローカル経路は token 無しの既定経路なので実害が大きい）。
    """
    import re

    repo_path = tmp_path / "repo"
    target = repo_path / "file.py"
    target.parent.mkdir(parents=True)
    target.write_text("before", encoding="utf-8")
    fake_git = DummyGitModule()
    monkeypatch.setitem(sys.modules, "git", SimpleNamespace(Repo=fake_git.Repo))

    result = agent._apply_local_change(
        repo_path, "file.py", "after", "summary", {"title": "キャッシュ層を改善する"}
    )

    branch = result["branch"]
    assert re.fullmatch(r"pantheon/improvement-[a-z0-9][a-z0-9-]*-\d{14}", branch), branch
    assert "improvement---" not in branch  # '-' 退化していない
    assert fake_git.repos[0].git.checkout_calls[0] == ("-b", branch)


def test_apply_local_change_none_title_does_not_crash(
    tmp_path, monkeypatch, agent: ImprovementExecutorAgent
):
    """title=None でもローカル適用がクラッシュしない（旧コードは .lower() で AttributeError）。"""
    import re

    repo_path = tmp_path / "repo"
    target = repo_path / "file.py"
    target.parent.mkdir(parents=True)
    target.write_text("before", encoding="utf-8")
    fake_git = DummyGitModule()
    monkeypatch.setitem(sys.modules, "git", SimpleNamespace(Repo=fake_git.Repo))

    result = agent._apply_local_change(repo_path, "file.py", "after", "summary", {"title": None})

    assert re.fullmatch(r"pantheon/improvement-[a-z0-9][a-z0-9-]*-\d{14}", result["branch"])


def _run_local_change(agent, tmp_path, monkeypatch, suggestion):
    repo_path = tmp_path / "repo"
    target = repo_path / "file.py"
    target.parent.mkdir(parents=True)
    target.write_text("before", encoding="utf-8")
    fake_git = DummyGitModule()
    monkeypatch.setitem(sys.modules, "git", SimpleNamespace(Repo=fake_git.Repo))
    agent._apply_local_change(repo_path, "file.py", "after", "summary", suggestion)
    return fake_git.repos[0].index.commit_calls


def test_apply_local_change_none_title_commit_message_is_honest(
    tmp_path, monkeypatch, agent: ImprovementExecutorAgent
):
    """title=None のとき commit メッセージが literal 'refactor: None' にならない。

    旧コード ``f"refactor: {suggestion.get('title', 'Apply improvement')}"`` は **title キーが
    None 値で存在する**と default ではなく None を返し、``refactor: None`` という commit が
    git 履歴に残っていた（``.get(k, default)`` は None 値をガードしない罠）。
    """
    commits = _run_local_change(agent, tmp_path, monkeypatch, {"title": None})
    assert commits == ["refactor: Apply improvement"]
    assert "None" not in commits[0]


def test_apply_local_change_absent_title_commit_message_is_honest(
    tmp_path, monkeypatch, agent: ImprovementExecutorAgent
):
    """title キー不在でも commit メッセージが default に落ちる（既存の後方互換）。"""
    commits = _run_local_change(agent, tmp_path, monkeypatch, {})
    assert commits == ["refactor: Apply improvement"]
