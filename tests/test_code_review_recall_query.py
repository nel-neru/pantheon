"""C6-a: code_review の analyze 経路が C5 意味リコールへ query を配線することを保証する。

レビュー対象のコードから作った query を ``apply_skills_to_prompt`` 経由で
``MemoryBank.recall`` に渡し、過去 Playbook を「いま見ているコードとの関連度」で
再ランクできるようにする。query 未配線（休眠）への回帰を防ぐ。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from agents.code_review_agent import CodeReviewAgent
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


def _fake_provider() -> SimpleNamespace:
    return SimpleNamespace(
        generate=AsyncMock(return_value=SimpleNamespace(content=json.dumps({"suggestions": []})))
    )


def test_build_recall_query_includes_repo_name_and_bounds_length():
    repo = "pantheon"
    code = "x" * 10_000
    query = CodeReviewAgent._build_recall_query(repo, code, max_chars=2000)

    assert query.startswith("pantheon\n")
    # repo_name + newline + 高々 max_chars 文字のコード本文に有界化される
    assert len(query) == len("pantheon\n") + 2000


def test_build_recall_query_handles_short_context():
    query = CodeReviewAgent._build_recall_query("repo", "short code")
    assert query == "repo\nshort code"


def test_generate_suggestions_passes_recall_query_to_skill_prompt(monkeypatch):
    agent = CodeReviewAgent(_make_specialist())
    monkeypatch.setattr("agents.code_review_agent.get_llm_provider", lambda _name: _fake_provider())

    captured: dict[str, object] = {}

    def _spy(base_prompt, *, query=None):
        captured["base_prompt"] = base_prompt
        captured["query"] = query
        return base_prompt

    monkeypatch.setattr(agent, "apply_skills_to_prompt", _spy)

    _run(agent._generate_suggestions("def handler(): return 1", "myrepo"))

    # 配線の核心: query が渡され、レビュー対象（repo 名＋コード）由来であること。
    assert captured["query"] is not None
    assert "myrepo" in captured["query"]
    assert "def handler" in captured["query"]


def test_recall_query_is_byte_identical_to_helper(monkeypatch):
    """配線した query が _build_recall_query の出力と一致する（実装ドリフト防止）。"""
    agent = CodeReviewAgent(_make_specialist())
    monkeypatch.setattr("agents.code_review_agent.get_llm_provider", lambda _name: _fake_provider())

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        agent,
        "apply_skills_to_prompt",
        lambda base_prompt, *, query=None: captured.setdefault("query", query) or base_prompt,
    )

    code = "class A:\n    pass\n"
    _run(agent._generate_suggestions(code, "demo"))

    assert captured["query"] == CodeReviewAgent._build_recall_query("demo", code)


def test_recall_query_does_not_break_when_memory_empty(tmp_path, monkeypatch):
    """エントリが無いとき query を渡しても system prompt は変わらない（既存挙動を保つ）。

    MemoryBank を空の tmp home に隔離し、query 配線が空 recall で no-op であることを確認する。
    """
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    agent = CodeReviewAgent(_make_specialist())

    base = "BASE PROMPT"
    with_query = agent.apply_skills_to_prompt(base, query="def handler(): ...")
    without_query = agent.apply_skills_to_prompt(base)

    assert with_query == without_query
