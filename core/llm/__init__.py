"""
Pantheon - LLM facade (Claude Code only)

Historically this package exposed a multi-provider abstraction. Pantheon now has
a single execution backend: the local ``claude`` CLI (Claude Code). This module
keeps the old import surface (``get_llm_provider``, ``LLMMessage``,
``LLMResponse``, ``LLMConfig``) so existing call sites keep working, but every
provider resolves to :class:`core.runtime.claude_code.ClaudeCodeProvider`.

Example:
    from core.llm import get_llm_provider

    provider = get_llm_provider()              # always Claude Code
    response = await provider.generate(messages=[...])
"""

from __future__ import annotations

from typing import Any

from .base import LLMConfig, LLMMessage, LLMProvider, LLMResponse
from .json_extract import extract_json_object

__all__ = [
    "LLMProvider",
    "LLMMessage",
    "LLMResponse",
    "LLMConfig",
    "ClaudeCodeProvider",
    "ClaudeUnavailableError",
    "get_llm_provider",
    "claude_available",
    "claude_binary",
    "run_claude",
    "run_claude_sync",
    "extract_json_object",
]


def get_llm_provider(provider_name: str | None = None, config: "LLMConfig | None" = None):
    """Return the Claude Code execution backend.

    The ``provider_name`` argument is accepted for backwards compatibility and
    ignored — there is only one backend now.
    """
    from core.runtime.claude_code import ClaudeCodeProvider

    return ClaudeCodeProvider(config)


def __getattr__(name: str) -> Any:
    # Lazy re-export of the Claude Code helpers to avoid an import cycle
    # (core.runtime.claude_code imports core.llm.base at module load time).
    if name in {
        "ClaudeCodeProvider",
        "ClaudeUnavailableError",
        "claude_available",
        "claude_binary",
        "run_claude",
        "run_claude_sync",
    }:
        from core.runtime import claude_code

        return getattr(claude_code, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
