"""
tool_schema — プロバイダー非依存の tool（function calling）スキーマ変換

中立表現を `{"name", "description", "input_schema"}`（Anthropic ネイティブ形）と定め、
各プロバイダーのネイティブ形へ相互変換する。これにより呼び出し側はプロバイダーを
意識せず同じ tool 定義を渡せる（「どのAIでも全機能」の tool 部分の核）。

対応する入力形（いずれも受理）:
- 中立 / Anthropic: {"name", "description", "input_schema"}
- OpenAI: {"type": "function", "function": {"name", "description", "parameters"}}
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

__all__ = [
    "neutralize_tool",
    "to_openai_tools",
    "to_anthropic_tools",
    "to_openai_tool_choice",
    "to_anthropic_tool_choice",
    "parse_openai_tool_calls",
]

_EMPTY_SCHEMA: Dict[str, Any] = {"type": "object", "properties": {}, "required": []}

ToolChoice = Optional[Union[str, Dict[str, Any]]]


def neutralize_tool(tool: Dict[str, Any]) -> Dict[str, Any]:
    """任意形式の tool 定義を中立形 {name, description, input_schema} に正規化する。"""
    if isinstance(tool.get("function"), dict):
        fn = tool["function"]
        return {
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", fn.get("input_schema", dict(_EMPTY_SCHEMA))),
        }
    return {
        "name": tool["name"],
        "description": tool.get("description", ""),
        "input_schema": tool.get("input_schema", tool.get("parameters", dict(_EMPTY_SCHEMA))),
    }


def to_openai_tools(tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    """中立/Anthropic/OpenAI いずれの tool 定義も OpenAI 形 (type=function) へ変換する。"""
    if not tools:
        return None
    normalized: List[Dict[str, Any]] = []
    for tool in tools:
        if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
            normalized.append(tool)
            continue
        neutral = neutralize_tool(tool)
        normalized.append(
            {
                "type": "function",
                "function": {
                    "name": neutral["name"],
                    "description": neutral["description"],
                    "parameters": neutral["input_schema"],
                },
            }
        )
    return normalized


def to_anthropic_tools(tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    """中立/OpenAI いずれの tool 定義も Anthropic 形 (name/description/input_schema) へ変換する。"""
    if not tools:
        return None
    return [
        {
            "name": neutral["name"],
            "description": neutral["description"],
            "input_schema": neutral["input_schema"],
        }
        for neutral in (neutralize_tool(tool) for tool in tools)
    ]


def to_openai_tool_choice(tool_choice: ToolChoice) -> ToolChoice:
    """tool_choice を OpenAI 形へ変換する。"""
    if tool_choice is None:
        return None
    if isinstance(tool_choice, str):
        if tool_choice in {"auto", "none", "required"}:
            return tool_choice
        return {"type": "function", "function": {"name": tool_choice}}
    return tool_choice


def to_anthropic_tool_choice(tool_choice: ToolChoice) -> Optional[Dict[str, Any]]:
    """tool_choice を Anthropic 形 ({"type": "auto"|"any"|"none"|"tool", "name"?}) へ変換する。"""
    if tool_choice is None:
        return None
    if isinstance(tool_choice, dict):
        if tool_choice.get("type") == "tool" and tool_choice.get("name"):
            return tool_choice
        fn = tool_choice.get("function") if isinstance(tool_choice.get("function"), dict) else {}
        name = (fn or {}).get("name") or tool_choice.get("name")
        if name:
            return {"type": "tool", "name": name}
        choice_type = tool_choice.get("type")
        if choice_type in {"auto", "any", "none"}:
            return {"type": choice_type}
        return {"type": "auto"}
    if tool_choice in {"auto", "any", "none"}:
        return {"type": tool_choice}
    if tool_choice == "required":
        return {"type": "any"}
    return {"type": "tool", "name": tool_choice}


def parse_openai_tool_calls(choice_message: Any) -> Optional[List[Dict[str, Any]]]:
    """OpenAI 互換レスポンスの tool_calls を中立形 [{id, name, input}] へ変換する。

    arguments(JSON文字列)は可能なら dict へパースする。失敗時は文字列のまま保持。
    """
    if not getattr(choice_message, "tool_calls", None):
        return None

    parsed_calls: List[Dict[str, Any]] = []
    for tool_call in choice_message.tool_calls:
        raw_arguments = tool_call.function.arguments or "{}"
        try:
            arguments: Any = json.loads(raw_arguments)
        except (json.JSONDecodeError, TypeError):
            arguments = raw_arguments
        parsed_calls.append(
            {
                "id": tool_call.id,
                "name": tool_call.function.name,
                "input": arguments,
            }
        )
    return parsed_calls
