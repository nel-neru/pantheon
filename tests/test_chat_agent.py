from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from agents.base import AgentResult
import agents.agent_factory as agent_factory_module
import agents.chat_agent as chat_agent
import core.llm as llm_module
import core.orchestration.pre_task_orchestrator as orchestrator_module
from core.llm.base import LLMConfig


def test_load_llm_config_reports_claude_code_backend(tmp_path, monkeypatch):
    """Pantheon has a single backend (Claude Code) and reads only an optional model."""
    settings_file = tmp_path / "gui_settings.json"
    settings_file.write_text(
        json.dumps({"llm_model": "claude-opus-4-8"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(chat_agent, "SETTINGS_FILE", settings_file)
    monkeypatch.delenv("PANTHEON_DEFAULT_MODEL", raising=False)

    config = chat_agent._load_llm_config()

    assert config["provider"] == "claude_code"
    assert config["model"] == "claude-opus-4-8"
    # No API keys exist anymore; availability mirrors the claude CLI (disabled in tests).
    assert "api_key" not in config
    assert config["available"] is False


def test_load_llm_config_model_env_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_agent, "SETTINGS_FILE", tmp_path / "absent.json")
    monkeypatch.setenv("PANTHEON_DEFAULT_MODEL", "claude-sonnet-4-6")

    config = chat_agent._load_llm_config()

    assert config["provider"] == "claude_code"
    assert config["model"] == "claude-sonnet-4-6"


def test_handle_agent_task_routes_through_pre_task_orchestrator(monkeypatch):
    class FakeAgentFactory:
        def __init__(self, llm_client=None):
            self.llm_client = llm_client

        def create(self, agent_id):
            return SimpleNamespace(agent_id=agent_id)

    class FakeOrchestrator:
        def __init__(self, llm_client=None, agent_factory=None, **kwargs):
            self.llm_client = llm_client
            self.agent_factory = agent_factory

        def analyze(self, task_type, description, context=None):
            assert task_type == "code_review"
            assert "レビュー" in description
            assert context and context["max_files"] == 10
            return SimpleNamespace(
                recommended_pattern="review_loop",
                recommended_agent_ids=["agent:code_reviewer"],
            )

        async def execute(self, task, analysis, agent_factory=None):
            assert task.input["repo_path"]
            assert analysis.recommended_agent_ids == ["agent:code_reviewer"]
            assert agent_factory is not None
            return AgentResult(
                success=True,
                output={
                    "files_reviewed": 2,
                    "suggestions": [
                        {"priority": "high", "title": "Fix auth", "file_path": "app.py"}
                    ],
                },
                thinking_process="reviewed successfully",
            )

    monkeypatch.setattr(agent_factory_module, "AgentFactory", FakeAgentFactory)
    monkeypatch.setattr(orchestrator_module, "PreTaskOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        llm_module,
        "get_llm_provider",
        lambda provider_name=None, config=None: SimpleNamespace(provider_name="claude_code"),
    )

    # available=True simulates a machine where the `claude` CLI is installed.
    config = {"provider": "claude_code", "model": "", "available": True}

    result = asyncio.run(chat_agent._handle_agent_task("このリポジトリのコードをレビューして", config))

    assert "🧭 PreTaskOrchestrator: code_review" in result
    assert "🤖 推奨エージェント: agent:code_reviewer" in result
    assert "✅ 2 ファイルをレビューしました" in result
    assert "Fix auth" in result
    assert "reviewed successfully" in result


def test_chat_session_reports_missing_claude_code(monkeypatch):
    monkeypatch.setattr(
        chat_agent,
        "_load_llm_config",
        lambda: {"provider": "claude_code", "model": "", "available": False},
    )

    session = chat_agent.ChatSession()
    result = asyncio.run(session.send("こんにちは"))

    assert "Claude Code" in result
    assert "claude" in result


def test_agent_factory_passes_provider_name_to_implementation(monkeypatch):
    class DummyImplementation:
        def __init__(self, specialist, provider_name="claude_code"):
            self.specialist = specialist
            self.provider_name = provider_name

    class FakeLoader:
        def get(self, capability_id):
            return SimpleNamespace(
                name="DummyAgent",
                description="dummy",
                skills=["codebase_exploration", "performance_analysis"],
                implementation="dummy.module.DummyImplementation",
            )

    factory = agent_factory_module.AgentFactory(llm_client=SimpleNamespace(provider_name="claude_code"))
    monkeypatch.setattr(factory, "_get_agent_loader", lambda: FakeLoader())
    monkeypatch.setattr(agent_factory_module, "_import_class", lambda path: DummyImplementation)

    agent = factory.create("agent:dummy")

    assert isinstance(agent, DummyImplementation)
    assert agent.provider_name == "claude_code"


def test_get_llm_provider_returns_claude_code():
    provider = llm_module.get_llm_provider(
        "anything",
        config=LLMConfig(default_model="claude-opus-4-8"),
    )

    assert provider.provider_name == "claude_code"


def test_handle_slash_command_returns_unknown_command_message():
    session = chat_agent.ChatSession()

    result = asyncio.run(chat_agent.handle_slash_command("/does-not-exist", session))

    assert result == "❓ 未知のコマンド '/does-not-exist'。/help でコマンド一覧を確認してください。"


def test_handle_slash_command_returns_none_for_empty_input():
    session = chat_agent.ChatSession()

    result = asyncio.run(chat_agent.handle_slash_command("   ", session))

    assert result is None
