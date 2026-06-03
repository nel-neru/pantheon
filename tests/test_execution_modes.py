"""Tests for execution-mode infra (cli_registry + /api/execution/modes)."""

from __future__ import annotations

from fastapi.testclient import TestClient

import web.server as server
from core.execution.cli_registry import (
    CLI_TOOLS,
    EXECUTION_MODES,
    all_cli_tools,
    get_cli_tool,
    is_command_available,
    resolve_cli_command,
)

client = TestClient(server.app)


def test_execution_modes_constant():
    assert EXECUTION_MODES == ["api", "cli"]


def test_known_cli_tools():
    assert {"claude", "codex", "gemini", "aider", "opencode"} <= set(CLI_TOOLS)
    assert get_cli_tool("claude").command == "claude"
    assert get_cli_tool("nope") is None


def test_resolve_cli_command_override():
    assert resolve_cli_command("claude") == "claude"
    assert resolve_cli_command("claude", {"cli_commands": {"claude": "claude-beta"}}) == "claude-beta"
    assert resolve_cli_command("unknown") is None


def test_is_command_available_for_nonexistent():
    assert is_command_available("definitely-not-a-real-cmd-xyz") is False
    assert is_command_available("") is False


def test_all_cli_tools_has_availability_flag():
    tools = all_cli_tools()
    assert len(tools) == len(CLI_TOOLS)
    for tool in tools:
        assert "available" in tool and isinstance(tool["available"], bool)
        assert "resolved_command" in tool


def test_api_execution_modes_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    response = client.get("/api/execution/modes")
    assert response.status_code == 200
    body = response.json()
    assert body["modes"] == ["api", "cli"]
    assert body["default_mode"] == "api"
    assert body["current"]["execution_mode"] in {"api", "cli"}
    ids = {tool["id"] for tool in body["cli_tools"]}
    assert {"claude", "codex", "gemini"} <= ids


def test_settings_roundtrip_execution_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY", "GITHUB_TOKEN", "GOOGLE_API_KEY"]:
        monkeypatch.delenv(key, raising=False)

    put = client.put("/api/settings", json={"execution_mode": "cli", "cli_tool": "codex"})
    assert put.status_code == 200

    got = client.get("/api/settings").json()
    assert got["execution_mode"] == "cli"
    assert got["cli_tool"] == "codex"


def test_settings_rejects_invalid_execution_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    resp = client.put("/api/settings", json={"execution_mode": "bogus"})
    assert resp.status_code == 422
