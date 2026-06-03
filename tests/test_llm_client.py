"""Unit tests for the provider-agnostic LLM bridge (core/llm/client.py, json_extract.py)."""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional

import pytest

from core.llm import (
    LLMClient,
    extract_json,
    extract_json_object,
    get_default_llm_client,
    resolve_default_provider,
    resolve_provider_api_key,
)
from core.llm.base import LLMConfig, LLMMessage, LLMProvider, LLMResponse
from core.llm.client import (
    _coerce_messages,
    _run_sync,
    get_configured_llm_provider,
    reset_provider_cache,
)
from core.llm.json_extract import strip_code_fences

_ENV_KEYS = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GROQ_API_KEY",
    "GITHUB_TOKEN",
    "GOOGLE_API_KEY",
    "REPOCORP_DEFAULT_LLM_PROVIDER",
    "REPOCORP_DEFAULT_MODEL",
]


class FakeProvider(LLMProvider):
    """最後に受け取ったメッセージを記録し、固定文字列を返す検証用プロバイダー。"""

    def __init__(self, content: str = '{"ok": true}') -> None:
        self._content = content
        self.last_messages: List[LLMMessage] | None = None
        self.last_kwargs: Dict[str, Any] = {}

    @property
    def provider_name(self) -> str:
        return "fake"

    def get_model_name(self, task_type: str = "default") -> str:
        return "fake-model"

    async def generate(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        self.last_messages = messages
        self.last_kwargs = {"temperature": temperature, "max_tokens": max_tokens, **kwargs}
        return LLMResponse(content=self._content, model="fake-model")

    async def stream(self, messages, model=None, temperature=0.7, max_tokens=None, **kwargs) -> AsyncIterator[str]:  # type: ignore[override]
        yield self._content


# --------------------------------------------------------------------------- #
# json_extract
# --------------------------------------------------------------------------- #


def test_extract_plain_json_object():
    assert extract_json_object('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_extract_json_object_with_code_fence():
    text = "```json\n{\"a\": 1}\n```"
    assert extract_json_object(text) == {"a": 1}


def test_extract_json_object_with_preamble_and_trailing_text():
    text = 'Sure! Here is the result:\n{"a": 1, "nested": {"b": 2}} -- done'
    assert extract_json_object(text) == {"a": 1, "nested": {"b": 2}}


def test_extract_json_object_returns_none_for_non_json():
    assert extract_json_object("no json here") is None
    assert extract_json_object("") is None


def test_extract_json_handles_arrays():
    assert extract_json("```\n[1, 2, 3]\n```") == [1, 2, 3]
    assert extract_json('prefix [{"x": 1}] suffix') == [{"x": 1}]


def test_strip_code_fences_passthrough_when_no_fence():
    assert strip_code_fences("  hello  ") == "hello"


# --------------------------------------------------------------------------- #
# LLMClient
# --------------------------------------------------------------------------- #


def test_coerce_messages_from_string():
    msgs = _coerce_messages("hello")
    assert len(msgs) == 1 and msgs[0].role == "user" and msgs[0].content == "hello"


def test_coerce_messages_from_dicts_and_objects():
    msgs = _coerce_messages([
        {"role": "system", "content": "sys"},
        LLMMessage(role="user", content="hi"),
    ])
    assert [m.role for m in msgs] == ["system", "user"]
    assert [m.content for m in msgs] == ["sys", "hi"]


def test_client_invoke_returns_response_with_content():
    client = LLMClient(FakeProvider(content="hello world"))
    response = client.invoke("ping")
    assert response.content == "hello world"


def test_client_complete_returns_string():
    client = LLMClient(FakeProvider(content="answer"))
    assert client.complete([LLMMessage(role="user", content="q")]) == "answer"


def test_client_invoke_accepts_message_dict_list():
    provider = FakeProvider()
    client = LLMClient(provider)
    client.invoke([{"role": "user", "content": "hi"}])
    assert provider.last_messages is not None
    assert provider.last_messages[0].content == "hi"


def test_client_generate_json():
    client = LLMClient(FakeProvider(content='```json\n{"ok": true}\n```'))
    assert client.generate_json("give me json") == {"ok": True}


def test_client_generate_json_raises_on_non_json():
    client = LLMClient(FakeProvider(content="not json"))
    with pytest.raises(ValueError):
        client.generate_json("x")


def test_client_default_temperature_passed_through():
    provider = FakeProvider()
    LLMClient(provider, temperature=0.15).invoke("x")
    assert provider.last_kwargs["temperature"] == 0.15


def test_client_provider_name_exposed():
    assert LLMClient(FakeProvider()).provider_name == "fake"


async def test_client_invoke_works_inside_running_loop():
    """FastAPI など実行中ループ内から同期 invoke を呼んでも例外にならない。"""
    client = LLMClient(FakeProvider(content="loop-ok"))
    # この関数自体が asyncio.run 配下（実行中ループあり）で動く
    response = client.invoke("ping")
    assert response.content == "loop-ok"


async def test_client_ainvoke():
    client = LLMClient(FakeProvider(content="async-ok"))
    response = await client.ainvoke("ping")
    assert response.content == "async-ok"


def test_run_sync_without_running_loop():
    async def _coro():
        return 42

    assert _run_sync(_coro()) == 42


# --------------------------------------------------------------------------- #
# default client resolution
# --------------------------------------------------------------------------- #


@pytest.fixture
def clean_env(monkeypatch):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_get_default_llm_client_returns_none_without_key(clean_env):
    assert get_default_llm_client(settings={}) is None


def test_get_default_llm_client_with_key_from_settings(clean_env):
    client = get_default_llm_client(
        settings={"llm_provider": "anthropic", "anthropic_api_key": "sk-test-123"}
    )
    assert isinstance(client, LLMClient)
    assert client.provider_name == "anthropic"


def test_get_default_llm_client_with_env_key(clean_env):
    clean_env.setenv("OPENAI_API_KEY", "sk-openai-test")
    client = get_default_llm_client(settings={"llm_provider": "openai"})
    assert isinstance(client, LLMClient)
    assert client.provider_name == "openai"


def test_get_default_llm_client_nested_api_keys(clean_env):
    client = get_default_llm_client(
        settings={"llm_provider": "groq", "api_keys": {"groq": "gsk-test"}}
    )
    assert isinstance(client, LLMClient)
    assert client.provider_name == "groq"


def test_resolve_default_provider_falls_back_to_anthropic(clean_env):
    assert resolve_default_provider(settings={}) == "anthropic"
    assert resolve_default_provider(settings={"llm_provider": "unknown"}) == "anthropic"
    assert resolve_default_provider(settings={"llm_provider": "gemini"}) == "gemini"


def test_resolve_provider_api_key_precedence(clean_env):
    clean_env.setenv("ANTHROPIC_API_KEY", "env-key")
    # settings top-level key takes precedence over env
    assert resolve_provider_api_key("anthropic", settings={"anthropic_api_key": "settings-key"}) == "settings-key"
    # env used when settings absent
    assert resolve_provider_api_key("anthropic", settings={}) == "env-key"


# --------------------------------------------------------------------------- #
# LLMConfig.from_settings (B1) / provider cache (B11)
# --------------------------------------------------------------------------- #


def test_llm_config_from_settings_resolves_provider_key_model(clean_env):
    cfg = LLMConfig.from_settings(
        {"llm_provider": "openai", "openai_api_key": "sk-x", "llm_model": "gpt-4o"}
    )
    assert cfg.default_provider == "openai"
    assert cfg.api_keys == {"openai": "sk-x"}
    assert cfg.default_model == "gpt-4o"


def test_llm_config_from_settings_without_key_has_empty_keys(clean_env):
    cfg = LLMConfig.from_settings({"llm_provider": "openai"})
    assert cfg.default_provider == "openai"
    assert cfg.api_keys == {}


def test_get_configured_provider_is_cached_and_resettable(clean_env):
    reset_provider_cache()
    settings = {"llm_provider": "anthropic", "anthropic_api_key": "sk-cache-unique-1"}
    p1 = get_configured_llm_provider(settings=settings)
    p2 = get_configured_llm_provider(settings=settings)
    assert p1 is not None and p1 is p2  # 同一 (provider, key, model) はキャッシュ
    reset_provider_cache()
    p3 = get_configured_llm_provider(settings=settings)
    assert p3 is not p1  # reset 後は新規生成
