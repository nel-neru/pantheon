"""
Pantheon - LLM message/response value objects (Claude Code only)

The provider abstraction is gone: Pantheon runs every generation through the
local ``claude`` CLI (see :mod:`core.runtime.claude_code`). These small value
objects remain because the rest of the codebase passes them around; they no
longer carry any API-key / hosted-provider configuration.
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
    model: str = "claude-code"
    usage: Optional[Dict[str, int]] = None  # prompt_tokens, completion_tokens, total_tokens
    finish_reason: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None

    def __str__(self) -> str:  # several call sites do str(response)
        return self.content or ""


class LLMProvider(ABC):
    """Abstract execution backend.

    Retained for typing/duck-compat only; the sole concrete implementation is
    :class:`core.runtime.claude_code.ClaudeCodeProvider`.
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
        """Generate a single response."""

    @abstractmethod
    async def stream(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a response."""

    @abstractmethod
    def get_model_name(self, task_type: str = "default") -> str:
        """Return the model name for a task type."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Backend name (always ``claude_code``)."""


class LLMConfig:
    """Lightweight, secret-free runtime config.

    Kept for backwards compatibility with call sites that construct it. The only
    meaningful field today is ``default_model`` (optional ``--model`` passed to
    the ``claude`` CLI). ``api_keys`` is accepted but ignored.
    """

    def __init__(
        self,
        default_provider: str = "claude_code",
        default_model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        api_keys: Optional[Dict[str, str]] = None,
    ):
        self.default_provider = "claude_code"
        self.default_model = default_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_keys = {}  # intentionally empty: Pantheon uses no API keys

    @classmethod
    def from_env(cls) -> "LLMConfig":
        import os

        return cls(default_model=os.getenv("PANTHEON_DEFAULT_MODEL") or None)
