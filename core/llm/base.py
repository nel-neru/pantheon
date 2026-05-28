"""
RepoCorp AI - LLM Provider Abstraction Layer

すべてのLLM呼び出しをこのインターフェース経由で行う。
将来的にローカルLLMや他のプロバイダを追加する際も、
このインターフェースを実装するだけで切り替え可能。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional


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
        **kwargs: Any,
    ) -> LLMResponse:
        """単発の応答を生成"""
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
