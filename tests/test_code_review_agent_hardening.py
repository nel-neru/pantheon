from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.code_review_agent import CodeImprovementSuggestion, CodeReviewAgent
from core.models.organization import AgentSkill, SpecialistAgent


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


def _make_specialist() -> SpecialistAgent:
    return SpecialistAgent(
        name="Reviewer",
        skills=[AgentSkill.CODEBASE_EXPLORATION, AgentSkill.DEEP_RESEARCH],
    )


@pytest.mark.parametrize("priority", ["urgent", "", "LOWEST"])
def test_code_improvement_suggestion_rejects_invalid_priority(priority: str):
    with pytest.raises(ValueError):
        CodeImprovementSuggestion(
            title="Bad priority",
            description="desc",
            file_path="src/app.py",
            priority=priority,
            category="security",
        )


def test_code_improvement_suggestion_rejects_invalid_category():
    with pytest.raises(ValueError):
        CodeImprovementSuggestion(
            title="Bad category",
            description="desc",
            file_path="src/app.py",
            priority="medium",
            category="unknown",
        )


@pytest.mark.parametrize("file_path", ["/etc/passwd", "../secrets.py", "C:/windows/system32.txt"])
def test_code_improvement_suggestion_rejects_non_relative_paths(file_path: str):
    with pytest.raises(ValueError):
        CodeImprovementSuggestion(
            title="Bad path",
            description="desc",
            file_path=file_path,
            priority="medium",
            category="security",
        )


def test_code_improvement_suggestion_normalizes_windows_relative_path():
    suggestion = CodeImprovementSuggestion(
        title="Normalize path",
        description="desc",
        file_path=r"src\module.py",
        priority="HIGH",
        category="Security",
    )

    assert suggestion.file_path == "src/module.py"
    assert suggestion.priority == "high"
    assert suggestion.category == "security"


def test_collect_code_files_skips_symlinks(tmp_path: Path):
    real_file = tmp_path / "main.py"
    real_file.write_text("print('ok')\n", encoding="utf-8")

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "leak.py").write_text("print('leak')\n", encoding="utf-8")

    try:
        (tmp_path / "linked.py").symlink_to(real_file)
        (tmp_path / "escape").symlink_to(outside_dir, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not supported in this environment")

    files = CodeReviewAgent(_make_specialist())._collect_code_files(tmp_path, max_files=10)

    assert "main.py" in files
    assert "linked.py" not in files
    assert "escape/leak.py" not in files


def test_generate_suggestions_skips_invalid_llm_entries(monkeypatch):
    agent = CodeReviewAgent(_make_specialist())
    fake_provider = SimpleNamespace(
        generate=AsyncMock(
            return_value=SimpleNamespace(
                content=json.dumps(
                    {
                        "suggestions": [
                            {
                                "title": "Valid",
                                "description": "desc",
                                "file_path": "src/app.py",
                                "priority": "high",
                                "category": "security",
                                "expected_impact": "impact",
                            },
                            {
                                "title": "Invalid",
                                "description": "desc",
                                "file_path": "../escape.py",
                                "priority": "high",
                                "category": "security",
                            },
                        ]
                    }
                )
            )
        )
    )
    monkeypatch.setattr(
        "agents.code_review_agent.get_llm_provider", lambda _provider_name: fake_provider
    )

    suggestions = _run(agent._generate_suggestions("code", "repo"))

    assert [suggestion.title for suggestion in suggestions] == ["Valid"]
