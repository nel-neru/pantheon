"""Tests for provider-agnostic tool schema conversion (core/llm/tool_schema.py)."""

from __future__ import annotations

from types import SimpleNamespace

from core.llm.tool_schema import (
    neutralize_tool,
    parse_openai_tool_calls,
    to_anthropic_tool_choice,
    to_anthropic_tools,
    to_openai_tool_choice,
    to_openai_tools,
)

NEUTRAL_TOOL = {
    "name": "search",
    "description": "Search the web",
    "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
}
OPENAI_TOOL = {
    "type": "function",
    "function": {
        "name": "search",
        "description": "Search the web",
        "parameters": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
    },
}


def test_neutralize_from_openai():
    assert neutralize_tool(OPENAI_TOOL) == NEUTRAL_TOOL


def test_neutralize_from_neutral():
    assert neutralize_tool(NEUTRAL_TOOL) == NEUTRAL_TOOL


def test_to_openai_tools_from_neutral():
    result = to_openai_tools([NEUTRAL_TOOL])
    assert result == [OPENAI_TOOL]


def test_to_openai_tools_passthrough_openai():
    assert to_openai_tools([OPENAI_TOOL]) == [OPENAI_TOOL]


def test_to_anthropic_tools_from_openai():
    result = to_anthropic_tools([OPENAI_TOOL])
    assert result == [NEUTRAL_TOOL]


def test_to_anthropic_tools_from_neutral():
    assert to_anthropic_tools([NEUTRAL_TOOL]) == [NEUTRAL_TOOL]


def test_empty_tools_return_none():
    assert to_openai_tools(None) is None
    assert to_openai_tools([]) is None
    assert to_anthropic_tools(None) is None


def test_openai_tool_choice():
    assert to_openai_tool_choice(None) is None
    assert to_openai_tool_choice("auto") == "auto"
    assert to_openai_tool_choice("required") == "required"
    assert to_openai_tool_choice("search") == {"type": "function", "function": {"name": "search"}}


def test_anthropic_tool_choice_from_string():
    assert to_anthropic_tool_choice(None) is None
    assert to_anthropic_tool_choice("auto") == {"type": "auto"}
    assert to_anthropic_tool_choice("any") == {"type": "any"}
    assert to_anthropic_tool_choice("required") == {"type": "any"}
    assert to_anthropic_tool_choice("search") == {"type": "tool", "name": "search"}


def test_anthropic_tool_choice_from_openai_dict():
    openai_choice = {"type": "function", "function": {"name": "search"}}
    assert to_anthropic_tool_choice(openai_choice) == {"type": "tool", "name": "search"}


def test_parse_openai_tool_calls_parses_arguments():
    message = SimpleNamespace(
        tool_calls=[
            SimpleNamespace(
                id="call_1",
                function=SimpleNamespace(name="search", arguments='{"q": "hello"}'),
            )
        ]
    )
    calls = parse_openai_tool_calls(message)
    assert calls == [{"id": "call_1", "name": "search", "input": {"q": "hello"}}]


def test_parse_openai_tool_calls_keeps_invalid_json_as_string():
    message = SimpleNamespace(
        tool_calls=[
            SimpleNamespace(id="c", function=SimpleNamespace(name="f", arguments="not-json"))
        ]
    )
    calls = parse_openai_tool_calls(message)
    assert calls == [{"id": "c", "name": "f", "input": "not-json"}]


def test_parse_openai_tool_calls_none_when_absent():
    assert parse_openai_tool_calls(SimpleNamespace(tool_calls=None)) is None
