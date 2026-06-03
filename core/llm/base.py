"""
RepoCorp AI - LLM Provider Abstraction Layer

すべてのLLM呼び出しをこのインターフェース経由で行う。
将来的にローカルLLMや他のプロバイダを追加する際も、
このインターフェースを実装するだけで切り替え可能。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMMessage:
    role: str  # "system", "user", "assistant", "tool"
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None  # prompt_tokens, completion_tokens, total_tokens
    finish_reason: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class LLMProvider(ABC):
    """
    LLMプロバイダーの抽象基底クラス。
    すべての実装はこのインターフェースに従う。
    """

    @abstractmethod
    async def generate(
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
        """単発の応答を生成。

        json_mode=True かつ provider が対応する場合はネイティブな構造化出力
        （response_format / response_mime_type 等）を要求する。非対応の provider は
        無視してよい（呼び出し側が堅牢抽出にフォールバックする）。
        """
        pass

    @abstractmethod
    async def stream(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """ストリーミング応答"""
        pass

    @abstractmethod
    def get_model_name(self, task_type: str = "default") -> str:
        """タスク種別に応じたモデル名を返す（設定駆動）"""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """プロバイダー名（例: openai, anthropic）"""
        pass

    @property
    def capabilities(self) -> "Any":
        """このプロバイダーの能力記述（ProviderCapabilities）を返す。

        provider_name をキーに core/llm/capabilities.py のレジストリから取得する。
        UI/オーケストレーターが「このプロバイダーで何ができるか」を判断するために使う。
        """
        from .capabilities import get_capabilities

        return get_capabilities(self.provider_name)

    async def generate_json(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """JSONオブジェクトを返すことを期待する生成。プロバイダー差を吸収する。

        provider が `capabilities.supports_json_mode` を宣言していれば、まずネイティブな
        JSONモード（response_format / response_mime_type 等）で要求する。ネイティブモードが
        無い/失敗した場合は通常生成にフォールバックする。いずれの経路でも最終的には
        出力テキストから堅牢にJSONオブジェクトを抽出する（コードフェンスや前置き文を許容）。
        抽出に失敗した場合は ValueError を送出する。
        """
        from .json_extract import extract_json_object

        use_native = bool(getattr(self.capabilities, "supports_json_mode", False))
        response = None
        if use_native:
            try:
                response = await self.generate(
                    messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=True,
                    **kwargs,
                )
            except Exception as exc:  # noqa: BLE001 - ネイティブ非対応モデル等は通常生成へ
                logger.debug(
                    "native json mode failed for provider '%s' (%s); falling back to plain generation",
                    self.provider_name,
                    exc,
                )
                response = None
        if response is None:
            response = await self.generate(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
        data = extract_json_object(response.content)
        if data is None:
            raise ValueError(
                f"Provider '{self.provider_name}' returned non-JSON content "
                f"(first 200 chars: {response.content[:200]!r})"
            )
        return data


class LLMConfig:
    """
    LLM関連の設定を一元管理。
    将来的にYAMLやGUIから読み込めるように設計。
    """

    def __init__(
        self,
        default_provider: str = "anthropic",
        default_model: str = "claude-3-5-sonnet-20241022",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        api_keys: Optional[Dict[str, str]] = None,
    ):
        self.default_provider = default_provider
        self.default_model = default_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_keys = api_keys or {}

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """環境変数から設定を読み込む（将来的にpydantic-settingsに移行）"""
        import os
        return cls(
            default_provider=os.getenv("REPOCORP_DEFAULT_LLM_PROVIDER", "anthropic"),
            default_model=os.getenv("REPOCORP_DEFAULT_MODEL", "claude-3-5-sonnet-20241022"),
            api_keys={
                "openai": os.getenv("OPENAI_API_KEY", ""),
                "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
                "groq": os.getenv("GROQ_API_KEY", ""),
                "github_models": os.getenv("GITHUB_TOKEN", ""),
                "gemini": os.getenv("GOOGLE_API_KEY", ""),
            },
        )

    @classmethod
    def from_settings(cls, settings: Optional[Dict[str, Any]] = None) -> "LLMConfig":
        """GUI設定（gui_settings.json）＋環境変数から設定を解決する（B1）。

        `from_env()` は環境変数しか見ないため、GUI で保存したキー/プロバイダー/モデルが
        効かない。この classmethod は `core/llm/client.py` の解決ロジック（env > settings の
        優先順）に委譲して、選択中プロバイダーのキーを `api_keys` に流し込む。
        循環 import を避けるため client は遅延 import する。
        """
        from .client import (
            resolve_default_model,
            resolve_default_provider,
            resolve_provider_api_key,
        )

        provider = resolve_default_provider(settings)
        api_key = resolve_provider_api_key(provider, settings)
        model = resolve_default_model(settings)
        return cls(
            default_provider=provider,
            default_model=model or cls().default_model,
            api_keys={provider: api_key} if api_key else {},
        )
