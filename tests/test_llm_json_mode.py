"""ネイティブJSONモード（B4）のテスト。

capabilities 連動でネイティブ構造化出力（response_format / response_mime_type）を
要求し、非対応/失敗時は堅牢抽出にフォールバックする契約を固定する。
ネットワークには出ず、SDK クライアントはフェイクで差し替える。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncIterator, Dict, List, Optional

from core.llm.base import LLMMessage, LLMProvider, LLMResponse
from core.llm.capabilities import ProviderCapabilities, get_capabilities
from core.llm.client import LLMClient
from core.llm.gemini_provider import GeminiProvider
from core.llm.json_mode import (
    GEMINI_JSON_MIME_TYPE,
    OPENAI_JSON_RESPONSE_FORMAT,
    ensure_json_keyword,
)
from core.llm.openai_provider import OpenAIProvider

# --------------------------------------------------------------------------- #
# capabilities フラグ
# --------------------------------------------------------------------------- #


def test_json_mode_capabilities_flags():
    # ネイティブ JSON モードを配線したプロバイダー
    for name in ["openai", "groq", "github_models", "gemini"]:
        assert get_capabilities(name).supports_json_mode is True, name
    # Anthropic は response_format 非対応 → 堅牢抽出で代替
    assert get_capabilities("anthropic").supports_json_mode is False


# --------------------------------------------------------------------------- #
# ensure_json_keyword
# --------------------------------------------------------------------------- #


def test_ensure_json_keyword_appends_when_absent():
    messages = [{"role": "user", "content": "give me the data"}]
    result = ensure_json_keyword(messages)
    assert result is not messages  # 元リストは不変
    assert len(result) == 2
    assert result[-1]["role"] == "system"
    assert "json" in result[-1]["content"].lower()


def test_ensure_json_keyword_noop_when_present():
    messages = [{"role": "user", "content": "Return JSON please"}]
    assert ensure_json_keyword(messages) is messages


# --------------------------------------------------------------------------- #
# base.generate_json: capabilities 連動 + フォールバック
# --------------------------------------------------------------------------- #


class _RecordingProvider(LLMProvider):
    """json_mode の受領を記録し、capabilities を上書きできる検証用プロバイダー。"""

    def __init__(
        self,
        *,
        supports_json_mode: bool,
        content: str = '{"ok": true}',
        fail_on_json_mode: bool = False,
    ) -> None:
        self._supports = supports_json_mode
        self._content = content
        self._fail_on_json_mode = fail_on_json_mode
        self.json_mode_calls: List[bool] = []

    @property
    def provider_name(self) -> str:
        return "rec"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(provider="rec", supports_json_mode=self._supports)

    def get_model_name(self, task_type: str = "default") -> str:
        return "rec-model"

    async def generate(  # type: ignore[override]
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        json_mode: bool = False,
        **kwargs: Any,
    ) -> LLMResponse:
        self.json_mode_calls.append(json_mode)
        if json_mode and self._fail_on_json_mode:
            raise RuntimeError("native json mode unsupported by model")
        return LLMResponse(content=self._content, model="rec-model")

    async def stream(self, messages, model=None, temperature=0.7, max_tokens=None, **kwargs) -> AsyncIterator[str]:  # type: ignore[override]
        yield self._content


async def test_generate_json_requests_native_mode_when_supported():
    provider = _RecordingProvider(supports_json_mode=True)
    data = await provider.generate_json([LLMMessage(role="user", content="data")])
    assert data == {"ok": True}
    assert provider.json_mode_calls == [True]


async def test_generate_json_skips_native_mode_when_unsupported():
    provider = _RecordingProvider(supports_json_mode=False)
    data = await provider.generate_json([LLMMessage(role="user", content="data")])
    assert data == {"ok": True}
    assert provider.json_mode_calls == [False]


async def test_generate_json_falls_back_when_native_mode_errors():
    provider = _RecordingProvider(supports_json_mode=True, fail_on_json_mode=True)
    data = await provider.generate_json([LLMMessage(role="user", content="data")])
    assert data == {"ok": True}
    # 1回目はネイティブ(失敗)、2回目は通常生成へフォールバック
    assert provider.json_mode_calls == [True, False]


def test_client_generate_json_routes_through_provider_native_path():
    provider = _RecordingProvider(supports_json_mode=True, content='```json\n{"ok": true}\n```')
    client = LLMClient(provider)
    assert client.generate_json("give me json") == {"ok": True}
    assert provider.json_mode_calls == [True]


# --------------------------------------------------------------------------- #
# OpenAI 互換プロバイダー: response_format の配線
# --------------------------------------------------------------------------- #


class _FakeOpenAIClient:
    """chat.completions.create の呼び出し引数を記録するフェイク。"""

    def __init__(self, content: str = '{"ok": true}') -> None:
        self._content = content
        self.last_kwargs: Dict[str, Any] = {}
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        self.last_kwargs = kwargs
        message = SimpleNamespace(content=self._content, tool_calls=None)
        choice = SimpleNamespace(message=message, finish_reason="stop")
        return SimpleNamespace(choices=[choice], model="gpt-4o", usage=None)


async def test_openai_provider_sets_response_format_in_json_mode():
    provider = OpenAIProvider(provider_name="openai")
    fake = _FakeOpenAIClient()
    provider._client = fake  # _get_client をバイパス
    response = await provider.generate(
        [LLMMessage(role="user", content="give me the data")], json_mode=True
    )
    assert response.content == '{"ok": true}'
    assert fake.last_kwargs["response_format"] == OPENAI_JSON_RESPONSE_FORMAT
    # "json" を含まないプロンプトなので system 指示が補われている
    assert any("json" in str(m["content"]).lower() for m in fake.last_kwargs["messages"])


async def test_openai_provider_omits_response_format_without_json_mode():
    provider = OpenAIProvider(provider_name="openai")
    fake = _FakeOpenAIClient()
    provider._client = fake
    await provider.generate([LLMMessage(role="user", content="hello")])
    assert "response_format" not in fake.last_kwargs


# --------------------------------------------------------------------------- #
# Gemini プロバイダー: response_mime_type の配線
# --------------------------------------------------------------------------- #


class _FakeGenaiModel:
    def __init__(self, store: Dict[str, Any], text: str) -> None:
        self._store = store
        self._text = text

    def generate_content(self, contents: Any, **kwargs: Any) -> Any:
        self._store["generation_config"] = kwargs.get("generation_config")
        return SimpleNamespace(candidates=[], text=self._text, usage_metadata=None)


class _FakeGenai:
    def __init__(self, text: str = '{"ok": true}') -> None:
        self._text = text
        self._store: Dict[str, Any] = {}

    def GenerativeModel(self, model_name=None, system_instruction=None, tools=None):  # noqa: N802
        return _FakeGenaiModel(self._store, self._text)

    @property
    def last_generation_config(self) -> Optional[Dict[str, Any]]:
        return self._store.get("generation_config")


async def test_gemini_provider_sets_response_mime_type_in_json_mode():
    provider = GeminiProvider()
    fake = _FakeGenai()
    provider._genai = fake  # _get_genai をバイパス
    response = await provider.generate(
        [LLMMessage(role="user", content="give me data")], json_mode=True
    )
    assert response.content == '{"ok": true}'
    assert fake.last_generation_config["response_mime_type"] == GEMINI_JSON_MIME_TYPE


async def test_gemini_provider_omits_mime_type_without_json_mode():
    provider = GeminiProvider()
    fake = _FakeGenai()
    provider._genai = fake
    await provider.generate([LLMMessage(role="user", content="hello")])
    assert "response_mime_type" not in (fake.last_generation_config or {})
