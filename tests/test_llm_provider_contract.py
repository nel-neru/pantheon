"""プロバイダー契約テスト（B12 / F1）。

5 プロバイダー（anthropic / openai / groq / github_models / gemini）の `generate()` が
共通契約—メッセージ整形・tool 中立化・tool_calls 正規化・json_mode 配線・usage 記録—を
満たすことを、SDK クライアントをフェイクに差し替えて（ネットワーク非依存で）固定する。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from core.llm.anthropic_provider import AnthropicProvider
from core.llm.base import LLMMessage
from core.llm.gemini_provider import GeminiProvider
from core.llm.github_models_provider import GitHubModelsProvider
from core.llm.openai_provider import OpenAIProvider

OPENAI_COMPATIBLE = ["openai", "groq", "github_models"]


def _make_openai_compatible(name: str):
    if name == "github_models":
        return GitHubModelsProvider()
    return OpenAIProvider(provider_name=name)


class _FakeOpenAIClient:
    def __init__(self, *, content: str = "ok", tool_calls: Any = None, usage: Any = None) -> None:
        self._content = content
        self._tool_calls = tool_calls
        self._usage = usage
        self.last_kwargs: Dict[str, Any] = {}
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        self.last_kwargs = kwargs
        message = SimpleNamespace(content=self._content, tool_calls=self._tool_calls)
        choice = SimpleNamespace(message=message, finish_reason="stop")
        return SimpleNamespace(choices=[choice], model="test-model", usage=self._usage)


# --------------------------------------------------------------------------- #
# OpenAI 互換 (openai / groq / github_models)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", OPENAI_COMPATIBLE)
async def test_openai_compatible_maps_messages_and_tools(name):
    provider = _make_openai_compatible(name)
    fake = _FakeOpenAIClient(content="hi")
    provider._client = fake
    tools = [{"name": "search", "description": "d", "input_schema": {"type": "object", "properties": {}}}]
    await provider.generate(
        [LLMMessage(role="system", content="s"), LLMMessage(role="user", content="u")],
        tools=tools,
        tool_choice="search",
    )
    sent = fake.last_kwargs
    assert sent["messages"] == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
    ]
    assert sent["tools"][0]["type"] == "function"
    assert sent["tools"][0]["function"]["name"] == "search"
    assert sent["tool_choice"] == {"type": "function", "function": {"name": "search"}}


@pytest.mark.parametrize("name", OPENAI_COMPATIBLE)
async def test_openai_compatible_parses_tool_calls(name):
    provider = _make_openai_compatible(name)
    tool_call = SimpleNamespace(
        id="call_1", function=SimpleNamespace(name="do", arguments='{"x": 1}')
    )
    fake = _FakeOpenAIClient(content="", tool_calls=[tool_call])
    provider._client = fake
    resp = await provider.generate([LLMMessage(role="user", content="u")])
    assert resp.tool_calls == [{"id": "call_1", "name": "do", "input": {"x": 1}}]


@pytest.mark.parametrize("name", OPENAI_COMPATIBLE)
async def test_openai_compatible_records_usage(name):
    provider = _make_openai_compatible(name)
    usage = SimpleNamespace(
        model_dump=lambda: {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}
    )
    fake = _FakeOpenAIClient(content="ok", usage=usage)
    provider._client = fake
    resp = await provider.generate([LLMMessage(role="user", content="u")])
    assert resp.usage["total_tokens"] == 5


@pytest.mark.parametrize("name", OPENAI_COMPATIBLE)
async def test_openai_compatible_json_mode_sets_response_format(name):
    provider = _make_openai_compatible(name)
    fake = _FakeOpenAIClient(content='{"ok": true}')
    provider._client = fake
    await provider.generate([LLMMessage(role="user", content="give data")], json_mode=True)
    assert fake.last_kwargs["response_format"] == {"type": "json_object"}


# --------------------------------------------------------------------------- #
# Anthropic
# --------------------------------------------------------------------------- #


class _FakeAnthropicClient:
    def __init__(self, *, blocks: List[Any], usage: Any = None) -> None:
        self._blocks = blocks
        self._usage = usage
        self.last_kwargs: Dict[str, Any] = {}
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kwargs: Any) -> Any:
        self.last_kwargs = kwargs
        return SimpleNamespace(
            content=self._blocks, model="claude-test", usage=self._usage, stop_reason="end_turn"
        )


async def test_anthropic_extracts_system_and_normalizes_tools():
    provider = AnthropicProvider()
    fake = _FakeAnthropicClient(
        blocks=[SimpleNamespace(type="text", text="hello")],
        usage=SimpleNamespace(input_tokens=3, output_tokens=5),
    )
    provider._client = fake
    tools = [{"type": "function", "function": {"name": "search", "description": "d", "parameters": {"type": "object"}}}]
    resp = await provider.generate(
        [LLMMessage(role="system", content="sys"), LLMMessage(role="user", content="u")],
        tools=tools,
        tool_choice="search",
    )
    assert resp.content == "hello"
    assert fake.last_kwargs["system"] == "sys"
    assert fake.last_kwargs["tools"][0]["name"] == "search"
    assert "input_schema" in fake.last_kwargs["tools"][0]
    assert fake.last_kwargs["tool_choice"] == {"type": "tool", "name": "search"}
    assert resp.usage["total_tokens"] == 8


async def test_anthropic_parses_tool_use_blocks():
    provider = AnthropicProvider()
    fake = _FakeAnthropicClient(
        blocks=[SimpleNamespace(type="tool_use", id="t1", name="do", input={"x": 1})]
    )
    provider._client = fake
    resp = await provider.generate([LLMMessage(role="user", content="u")])
    assert resp.tool_calls == [{"id": "t1", "name": "do", "input": {"x": 1}}]


async def test_anthropic_json_mode_not_leaked_to_sdk():
    provider = AnthropicProvider()
    fake = _FakeAnthropicClient(blocks=[SimpleNamespace(type="text", text='{"ok": true}')])
    provider._client = fake
    await provider.generate([LLMMessage(role="user", content="u")], json_mode=True)
    assert "json_mode" not in fake.last_kwargs
    assert "response_format" not in fake.last_kwargs


# --------------------------------------------------------------------------- #
# Gemini
# --------------------------------------------------------------------------- #


async def test_gemini_maps_system_and_tools():
    provider = GeminiProvider()
    captured: Dict[str, Any] = {}

    class _Model:
        def __init__(self, **kw: Any) -> None:
            captured.update(kw)

        def generate_content(self, contents: Any, **kwargs: Any) -> Any:
            captured["contents"] = contents
            captured["generation_config"] = kwargs.get("generation_config")
            return SimpleNamespace(candidates=[], text="hi", usage_metadata=None)

    provider._genai = SimpleNamespace(GenerativeModel=lambda **kw: _Model(**kw))
    tools = [{"name": "search", "description": "d", "input_schema": {"type": "object"}}]
    resp = await provider.generate(
        [LLMMessage(role="system", content="sys"), LLMMessage(role="user", content="u")],
        tools=tools,
    )
    assert resp.content == "hi"
    assert captured["system_instruction"] == "sys"
    assert captured["tools"][0]["function_declarations"][0]["name"] == "search"
    assert captured["contents"] == [{"role": "user", "parts": ["u"]}]
