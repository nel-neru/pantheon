"""Tests for C2 tool registry: declared tools register as mcp_tool capabilities."""

from __future__ import annotations

from types import SimpleNamespace

from core.intelligence.capability_registry import CapabilityRegistry
from core.intelligence.tool_registry import scan_and_register_tools


def _defn(tools, mcp=None):
    return SimpleNamespace(tools=tools, mcp=mcp or {})


def test_registers_declared_tools_as_mcp_tool(tmp_path):
    reg = CapabilityRegistry(platform_home=tmp_path)
    defs = [
        _defn(["Read", "Grep", "Write"]),
        _defn(["mcp__docs__search"], {"servers": {"docs": {"read_only": True}}}),
    ]
    count = scan_and_register_tools(defs, reg)
    assert count == 4  # Read, Grep, Write, mcp__docs__search
    entries = {e.id: e for e in reg.list_all(capability_type="mcp_tool")}
    assert "tool:Read" in entries
    assert "tool:Write" in entries
    assert "mcp_tool:mcp__docs__search" in entries
    # classification surfaces in the description
    assert "read-only" in entries["tool:Read"].description
    assert "gated" in entries["tool:Write"].description
    assert "read-only" in entries["mcp_tool:mcp__docs__search"].description


def test_dedup_across_definitions(tmp_path):
    reg = CapabilityRegistry(platform_home=tmp_path)
    count = scan_and_register_tools([_defn(["Read"]), _defn(["Read", "Glob"])], reg)
    assert count == 2  # Read counted once, plus Glob


def test_tool_less_definitions_register_nothing(tmp_path):
    reg = CapabilityRegistry(platform_home=tmp_path)
    assert scan_and_register_tools([_defn([]), _defn([], {})], reg) == 0
