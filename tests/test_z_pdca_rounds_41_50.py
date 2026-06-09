from __future__ import annotations

import ast
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from pydantic import ValidationError

from agents.chat_agent import ChatSession, handle_slash_command
from agents.conversation_agent import ConversationAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.self_code_writer import SelfCodeWriter
from agents.tool_design_agent import ImplementationSpec
from commands import build_parser, discover_command_modules
from config.settings import load_config


def test_self_code_writer_validates_generated_code_and_warns_on_todo(monkeypatch, caplog):
    writer = SelfCodeWriter(llm_client=None)
    spec = ImplementationSpec(
        spec_id="spec:round41",
        class_name="GeneratedAgent",
        file_path="agents/generated_agent.py",
        method_signatures=["async def run(self, task: AgentTask) -> AgentResult"],
        description="Generated test agent",
        integration_points=[],
        required_imports=[],
        estimated_lines=20,
        gap_id="gap:round41",
    )

    parse_calls: list[str] = []
    real_parse = ast.parse

    def spy_parse(code: str, *args, **kwargs):
        parse_calls.append(code)
        return real_parse(code, *args, **kwargs)

    monkeypatch.setattr("agents.self_code_writer.ast.parse", spy_parse)

    with caplog.at_level(logging.WARNING):
        output = writer.write_code(spec)

    assert parse_calls
    assert any("placeholder TODO code" in record.message for record in caplog.records)
    ast.parse(output.code_content)


def test_self_code_writer_escapes_special_characters():
    writer = SelfCodeWriter(llm_client=None)

    escaped = writer._escape_string('quote" slash\\ line\ncarriage\r tab\t')

    assert escaped == 'quote\\" slash\\\\ line\\ncarriage\\r tab\\t'


def test_handle_slash_command_respects_quoted_arguments(monkeypatch, tmp_path):
    captured: dict[str, str] = {}

    async def fake_add(payload):
        captured.update(payload)
        return "ok"

    repo_path = tmp_path / "repo with spaces"
    session = ChatSession()
    monkeypatch.setattr("agents.chat_agent._tool_add_organization", fake_add)

    result = asyncio.run(handle_slash_command(f'/add "Demo Org" "{repo_path}"', session))

    assert result == "ok"
    assert captured == {"name": "Demo Org", "repo": str(repo_path)}
    assert session.current_org == "Demo Org"


def test_conversation_agent_logs_search_errors(caplog, tmp_path):
    class BrokenKnowledgeManager:
        def search(self, _keywords):
            raise RuntimeError("boom")

    agent = ConversationAgent(knowledge_manager=BrokenKnowledgeManager(), platform_home=tmp_path)

    with caplog.at_level(logging.WARNING):
        result = agent._search_knowledge(["risk"])

    assert result == []
    assert any("knowledge search failed" in record.message for record in caplog.records)


def test_orchestrator_describe_routing_uses_reasoning_fallback():
    agent = OrchestratorAgent.create()

    class FakeOrchestrator:
        def analyze(self, task_type, description):
            return SimpleNamespace(
                recommended_pattern="single_agent",
                recommended_agent_ids=["agent:demo"],
                complexity="low",
                spawn_new_agent=False,
                reasoning=f"reasoning for {task_type}: {description}",
            )

    agent._orchestrator = FakeOrchestrator()

    routing = agent.describe_routing("code_review", "inspect code")

    assert routing["reasoning"] == "reasoning for code_review: inspect code"


def test_commands_are_discovered_and_parser_assigns_handlers():
    modules = {module.__name__.rsplit(".", 1)[-1] for module in discover_command_modules()}
    parser = build_parser()
    # org add は担当ワークスペース（--repo）が必須（1 ws = 1 org モデル）。
    args = parser.parse_args(["org", "add", "--name", "DemoOrg", "--repo", "/tmp/demo"])

    assert {"chat", "goal", "orchestration", "org", "platform"}.issubset(modules)
    assert args.handler_name == "cmd_org_add"


def test_agents_package_exports_public_agent_classes():
    import agents

    for name in [
        "OrchestratorAgent",
        "CodebaseExplorerAgent",
        "SelfCodeWriter",
        "ToolDesignAgent",
        "ConversationAgent",
        "ChatSession",
        "GenericSkillAgent",
    ]:
        assert hasattr(agents, name)


def test_all_agent_definitions_use_capability_id_and_fields():
    definitions_dir = Path(__file__).resolve().parents[1] / "agents" / "definitions"

    for path in definitions_dir.glob("*.yaml"):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        response_format = payload.get("response_format", {})
        assert payload["capability_id"].startswith("agent:"), path.name
        assert "schema" not in response_format, path.name
        assert "fields" in response_format, path.name


def test_load_config_reads_all_validated_yaml_sections():
    repo_root = Path(__file__).resolve().parents[1]

    config = load_config(repo_root / "config" / "default.yaml", project_root=repo_root)

    assert "strategic_analyst" in config.personas
    assert "meta_improvement" in config.departments
    assert "strategic_planning" in config.skills


def test_load_config_validates_persona_schema(tmp_path):
    config_dir = tmp_path / "config"
    personas_dir = config_dir / "personas"
    departments_dir = config_dir / "departments"
    skills_dir = tmp_path / "skills"
    personas_dir.mkdir(parents=True)
    departments_dir.mkdir(parents=True)
    skills_dir.mkdir()

    (config_dir / "default.yaml").write_text("self_improvement: {}\n", encoding="utf-8")
    (personas_dir / "broken.yaml").write_text("name: Broken Persona\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        load_config(config_dir / "default.yaml", project_root=tmp_path)
