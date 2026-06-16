"""Tests for C2 tool-use/MCP: ToolSpec classification + claude_code seam wiring."""

from __future__ import annotations

from types import SimpleNamespace

from core.runtime.tool_config import GATED_TOOLS, READ_ONLY_TOOLS, ToolSpec, classify_tool


def test_classify_builtin_and_mcp():
    assert classify_tool("Read") == "read_only"
    assert classify_tool("Grep") == "read_only"
    assert classify_tool("Write") == "gated"
    assert classify_tool("Bash") == "gated"
    assert classify_tool("UnknownXYZ") == "gated"  # safe default
    # MCP tool gated unless its server is declared read-only
    assert classify_tool("mcp__docs__search") == "gated"
    assert classify_tool("mcp__docs__search", read_only_servers={"docs": True}) == "read_only"
    assert classify_tool("mcp__fs__write", read_only_servers={"fs": False}) == "gated"


def test_read_only_and_gated_sets_disjoint():
    assert READ_ONLY_TOOLS.isdisjoint(GATED_TOOLS)


def test_from_tools_separates_allowed_and_gated():
    spec = ToolSpec.from_tools(["Read", "Grep", "Write", "Bash"])
    assert spec.allowed == ["Read", "Grep"]
    assert spec.gated == ["Write", "Bash"]
    assert not spec.is_empty


def test_allow_gated_promotes_everything():
    spec = ToolSpec.from_tools(["Read", "Write"], allow_gated=True)
    assert spec.allowed == ["Read", "Write"]
    assert spec.gated == []


def test_all_gated_no_mcp_is_empty():
    # An agent that declares only gated tools (autonomous mode) enables nothing
    # -> is_empty so the fast-path is kept.
    spec = ToolSpec.from_tools(["Write", "Bash"])
    assert spec.allowed == []
    assert spec.is_empty


def test_to_argv_builds_flags_and_strips_read_only_key():
    mcp = {"servers": {"docs": {"command": "docs-server", "read_only": True}}}
    spec = ToolSpec.from_tools(["Read", "mcp__docs__search", "Write"], mcp)
    argv = spec.to_argv()
    assert "--mcp-config" in argv
    assert "--strict-mcp-config" in argv
    # the control key read_only must not leak into the CLI server config
    cfg_idx = argv.index("--mcp-config") + 1
    assert "read_only" not in argv[cfg_idx]
    assert "docs-server" in argv[cfg_idx]
    assert "--allowedTools" in argv
    allowed = argv[argv.index("--allowedTools") + 1]
    assert "Read" in allowed and "mcp__docs__search" in allowed
    assert "--disallowedTools" in argv  # Write is gated


def test_to_argv_pins_strict_mcp_even_without_servers():
    # Read-only tools, NO declared MCP servers -> still --mcp-config {} + --strict-mcp-config,
    # so the fast-path's ambient-MCP suppression isn't silently lost (the C2 review's Critical).
    argv = ToolSpec.from_tools(["Read"]).to_argv()
    assert "--strict-mcp-config" in argv
    assert argv[argv.index("--mcp-config") + 1] == "{}"


def test_gated_server_omitted_unless_allow_gated():
    mcp = {"servers": {"fs": {"command": "fs-srv"}}}  # no read_only -> gated server
    assert ToolSpec.from_tools([], mcp).mcp_servers == {}  # not spawned in autonomous mode
    assert "fs" in ToolSpec.from_tools([], mcp, allow_gated=True).mcp_servers


def test_from_definition_none_when_no_tools():
    assert ToolSpec.from_definition(SimpleNamespace(tools=[], mcp={})) is None
    spec = ToolSpec.from_definition(SimpleNamespace(tools=["Read"], mcp={}))
    assert spec is not None and spec.allowed == ["Read"]


# --------------------------------------------------------------------------- #
# claude_code seam: tool_spec forces fast=False and injects the real argv      #
# --------------------------------------------------------------------------- #


def _fake_proc(args):
    return SimpleNamespace(
        args=args,
        returncode=0,
        stdout='{"type":"result","subtype":"success","is_error":false,"result":"ok"}',
        stderr="",
    )


def _patch_cli(monkeypatch):
    import core.runtime.claude_code as cc

    monkeypatch.setenv("PANTHEON_SPANS_LOG", "off")
    monkeypatch.setenv("PANTHEON_CLAUDE_TIMING_LOG", "off")
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")
    monkeypatch.setattr(cc, "_fast_args", lambda: ["--strict-mcp-config", "--mcp-config", "{}"])
    monkeypatch.setattr(cc, "gate_bypassed", lambda: True)
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return _fake_proc(args)

    monkeypatch.setattr(cc.subprocess, "run", fake_run)
    return cc, captured


def _msgs():
    from core.llm import LLMMessage

    return [LLMMessage(role="user", content="hi")]


def test_tool_spec_bypasses_fast_path(monkeypatch):
    cc, captured = _patch_cli(monkeypatch)
    spec = ToolSpec.from_tools(["Read", "Grep"])
    cc.run_claude_sync(_msgs(), tool_spec=spec)
    args = captured["args"]
    assert "--allowedTools" in args
    assert "Read,Grep" in args
    # MCP stays pinned strict (ambient .mcp.json suppressed) and there is exactly ONE
    # --mcp-config — no collision between the fast-path's and ours.
    assert "--strict-mcp-config" in args
    assert args.count("--mcp-config") == 1


def test_no_tool_spec_keeps_fast_path(monkeypatch):
    cc, captured = _patch_cli(monkeypatch)
    cc.run_claude_sync(_msgs())
    args = captured["args"]
    assert "--strict-mcp-config" in args and "{}" in args  # fast-path intact
    assert "--allowedTools" not in args


def test_provider_invoke_forwards_tool_spec(monkeypatch):
    import core.runtime.claude_code as cc

    captured = {}

    def fake_sync(messages, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(content="ok", model="x", usage=None, finish_reason="stop")

    monkeypatch.setattr(cc, "run_claude_sync", fake_sync)
    spec = ToolSpec.from_tools(["Read"])
    cc.ClaudeCodeProvider().invoke(_msgs(), tool_spec=spec, extra_args=["--foo"])
    assert captured.get("tool_spec") is spec
    assert captured.get("extra_args") == ["--foo"]
