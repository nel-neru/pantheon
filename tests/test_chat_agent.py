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


def test_load_llm_config_reads_gui_settings_file(tmp_path, monkeypatch):
    settings_file = tmp_path / "gui_settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "llm_provider": "groq",
                "llm_model": "llama-3.1-8b-instant",
                "groq_api_key": "gsk-test-key",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(chat_agent, "SETTINGS_FILE", settings_file)
    monkeypatch.delenv("REPOCORP_DEFAULT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("REPOCORP_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    config = chat_agent._load_llm_config()

    assert config["provider"] == "groq"
    assert config["model"] == "llama-3.1-8b-instant"
    assert config["api_key"] == "gsk-test-key"
    assert config["api_keys"]["groq"] == "gsk-test-key"


def test_load_llm_config_supports_github_models_env_fallback(tmp_path, monkeypatch):
    settings_file = tmp_path / "gui_settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "llm_provider": "github_models",
                "llm_model": "gpt-4o-mini",
                "api_keys": {"github_models": "file-token"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(chat_agent, "SETTINGS_FILE", settings_file)
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    config = chat_agent._load_llm_config()

    assert config["provider"] == "github_models"
    assert config["api_key"] == "env-token"
    assert config["api_keys"]["github_models"] == "file-token"


def test_load_llm_config_reads_gemini_settings_file(tmp_path, monkeypatch):
    settings_file = tmp_path / "gui_settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "llm_provider": "gemini",
                "llm_model": "gemini-2.0-flash",
                "gemini_api_key": "AIza-test-key",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(chat_agent, "SETTINGS_FILE", settings_file)
    monkeypatch.delenv("REPOCORP_DEFAULT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("REPOCORP_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    config = chat_agent._load_llm_config()

    assert config["provider"] == "gemini"
    assert config["model"] == "gemini-2.0-flash"
    assert config["api_key"] == "AIza-test-key"
    assert config["api_keys"]["gemini"] == "AIza-test-key"


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
        lambda provider_name=None, config=None: SimpleNamespace(provider_name=provider_name or "openai"),
    )

    config = {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key": "sk-test",
        "api_keys": {"openai": "sk-test"},
    }

    result = asyncio.run(chat_agent._handle_agent_task("このリポジトリのコードをレビューして", config))

    assert "🧭 PreTaskOrchestrator: code_review" in result
    assert "🤖 推奨エージェント: agent:code_reviewer" in result
    assert "✅ 2 ファイルをレビューしました" in result
    assert "Fix auth" in result
    assert "reviewed successfully" in result


def test_chat_session_reports_provider_specific_missing_key(monkeypatch):
    monkeypatch.setattr(
        chat_agent,
        "_load_llm_config",
        lambda: {"provider": "groq", "model": "llama-3.1-8b-instant", "api_key": "", "api_keys": {}},
    )

    session = chat_agent.ChatSession()
    result = asyncio.run(session.send("こんにちは"))

    assert "GROQ_API_KEY" in result
    assert "APIキーが設定されていません" in result


def test_agent_factory_passes_provider_name_to_implementation(monkeypatch):
    class DummyImplementation:
        def __init__(self, specialist, provider_name="anthropic"):
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

    factory = agent_factory_module.AgentFactory(llm_client=SimpleNamespace(provider_name="groq"))
    monkeypatch.setattr(factory, "_get_agent_loader", lambda: FakeLoader())
    monkeypatch.setattr(agent_factory_module, "_import_class", lambda path: DummyImplementation)

    agent = factory.create("agent:dummy")

    assert isinstance(agent, DummyImplementation)
    assert agent.provider_name == "groq"


def test_get_llm_provider_supports_groq():
    provider = llm_module.get_llm_provider(
        "groq",
        config=LLMConfig(default_model="llama-3.1-8b-instant", api_keys={"groq": "gsk-test"}),
    )

    assert provider.provider_name == "groq"


def test_handle_slash_command_returns_unknown_command_message():
    session = chat_agent.ChatSession()

    result = asyncio.run(chat_agent.handle_slash_command("/does-not-exist", session))

    assert result == "❓ 未知のコマンド '/does-not-exist'。/help でコマンド一覧を確認してください。"


def test_handle_slash_command_returns_none_for_empty_input():
    session = chat_agent.ChatSession()

    result = asyncio.run(chat_agent.handle_slash_command("   ", session))

    assert result is None
