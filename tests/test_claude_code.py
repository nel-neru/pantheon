"""Tests for the Claude Code execution backend (core.runtime.claude_code).

These never invoke the real ``claude`` CLI: they either rely on the
session-wide disable flag (see tests/conftest.py) or monkeypatch the binary
resolver and ``subprocess.run`` to simulate the CLI deterministically.
"""

from __future__ import annotations

import asyncio
import json

import pytest

import core.runtime.claude_code as cc
from core.llm import LLMMessage, get_llm_provider
from core.runtime.claude_code import (
    ClaudeCodeProvider,
    ClaudeUnavailableError,
    claude_available,
    split_system_user,
)


def test_disabled_in_tests_by_default():
    # tests/conftest.py sets PANTHEON_NO_CLAUDE=1
    assert claude_available() is False
    assert cc.claude_binary() is None


def test_split_system_user_variants():
    assert split_system_user("hello") == (None, "hello")

    sys_text, user_text = split_system_user(
        [
            {"role": "system", "content": "S1"},
            {"role": "system", "content": "S2"},
            {"role": "user", "content": "U1"},
            {"role": "assistant", "content": "A1"},
        ]
    )
    assert sys_text == "S1\n\nS2"
    assert "U1" in user_text and "[assistant]" in user_text and "A1" in user_text

    sys_text, user_text = split_system_user(LLMMessage(role="user", content="just user"))
    assert sys_text is None
    assert user_text == "just user"


def test_provider_generate_raises_when_unavailable():
    provider = get_llm_provider()
    assert isinstance(provider, ClaudeCodeProvider)
    assert provider.provider_name == "claude_code"
    with pytest.raises(ClaudeUnavailableError):
        asyncio.run(provider.generate(messages=[LLMMessage(role="user", content="hi")]))


def test_invoke_raises_when_unavailable():
    provider = get_llm_provider()
    with pytest.raises(ClaudeUnavailableError):
        provider.invoke("hello")


def test_run_claude_sync_parses_json_result(monkeypatch):
    """With a faked binary + subprocess, the json ``result`` field is extracted."""
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")

    captured = {}

    class FakeProc:
        returncode = 0
        stdout = json.dumps({"type": "result", "result": "the answer", "is_error": False})
        stderr = ""

    def fake_run(args, **kwargs):
        captured["args"] = args
        return FakeProc()

    monkeypatch.setattr(cc.subprocess, "run", fake_run)

    response = cc.run_claude_sync(
        [LLMMessage(role="system", content="be terse"), LLMMessage(role="user", content="q")],
        model="claude-opus-4-8",
    )
    assert response.content == "the answer"
    assert response.model == "claude-opus-4-8"
    # headless, json output, system + model flags are wired through
    assert "-p" in captured["args"]
    assert "--output-format" in captured["args"] and "json" in captured["args"]
    assert "--append-system-prompt" in captured["args"]
    assert "--model" in captured["args"] and "claude-opus-4-8" in captured["args"]


def test_run_claude_sync_falls_back_to_raw_text(monkeypatch):
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")

    class FakeProc:
        returncode = 0
        stdout = "plain text answer"
        stderr = ""

    monkeypatch.setattr(cc.subprocess, "run", lambda args, **kw: FakeProc())
    response = cc.run_claude_sync("hello")
    assert response.content == "plain text answer"


def test_run_claude_sync_raises_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")

    class FakeProc:
        returncode = 2
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(cc.subprocess, "run", lambda args, **kw: FakeProc())
    with pytest.raises(ClaudeUnavailableError):
        cc.run_claude_sync("hello")
