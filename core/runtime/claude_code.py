"""
Pantheon — Claude Code execution backend.

Replaces the former multi-provider LLM API layer (Anthropic / OpenAI / Gemini /
Groq / GitHub Models SDKs). Every piece of "thinking" or generation goes through
the local ``claude`` CLI (Claude Code) running in headless / print mode
(``claude -p``). There are **no API keys and no hosted-API calls**.

The public surface intentionally mirrors the small contract that the rest of the
codebase already depends on, so existing call sites keep working unchanged:

* ``ClaudeCodeProvider.generate(messages=..., ...)``  — async, returns ``LLMResponse``
* ``ClaudeCodeProvider.ainvoke(messages)``            — async, returns ``LLMResponse``
* ``ClaudeCodeProvider.invoke(messages|str)``         — sync,  returns ``LLMResponse``
* ``ClaudeCodeProvider.complete(messages)``           — sync,  returns ``str``

When the ``claude`` CLI is unavailable (not installed, or disabled via the
``PANTHEON_NO_CLAUDE`` env var used in tests/CI), the provider raises
``ClaudeUnavailableError`` (for the async/generate path) so the existing
heuristic fallbacks in each agent take over, preserving offline behaviour.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from typing import Any, Optional, Sequence, Union

from core.llm.base import LLMMessage, LLMResponse

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Configuration (env-driven, no secrets)                                       #
# --------------------------------------------------------------------------- #
DISABLE_ENV = "PANTHEON_NO_CLAUDE"      # truthy => behave as if claude is absent
BIN_ENV = "PANTHEON_CLAUDE_BIN"          # override path / name of the claude binary
MODEL_ENV = "PANTHEON_DEFAULT_MODEL"     # optional default model passed to --model
TIMEOUT_ENV = "PANTHEON_CLAUDE_TIMEOUT"  # seconds for a single headless call

_TRUTHY = {"1", "true", "yes", "on"}


class ClaudeUnavailableError(RuntimeError):
    """Raised when the ``claude`` CLI cannot be used for a generation call."""


def _default_timeout() -> float:
    try:
        return float(os.getenv(TIMEOUT_ENV, "180"))
    except (TypeError, ValueError):
        return 180.0


def _is_disabled() -> bool:
    return os.getenv(DISABLE_ENV, "").strip().lower() in _TRUTHY


def claude_binary() -> Optional[str]:
    """Resolve the ``claude`` executable, or ``None`` if unavailable/disabled."""
    if _is_disabled():
        return None
    explicit = os.getenv(BIN_ENV)
    if explicit:
        if os.path.isabs(explicit):
            return explicit if os.path.exists(explicit) else None
        return shutil.which(explicit)
    return shutil.which("claude")


def claude_available() -> bool:
    """True when headless ``claude`` generation can be attempted."""
    return claude_binary() is not None


# --------------------------------------------------------------------------- #
# Message flattening                                                           #
# --------------------------------------------------------------------------- #
MessageLike = Union[str, LLMMessage, dict, Sequence[Any]]


def _coerce_one(item: Any) -> tuple[str, str]:
    """Return ``(role, content)`` for a single message-like item."""
    if isinstance(item, LLMMessage):
        return (item.role or "user"), (item.content or "")
    if isinstance(item, dict):
        return str(item.get("role") or "user"), str(item.get("content") or "")
    return "user", str(item)


def split_system_user(messages: MessageLike) -> tuple[Optional[str], str]:
    """Flatten arbitrary message input into ``(system_prompt, user_prompt)``.

    Accepts a bare string, a single ``LLMMessage``/dict, or a sequence of those.
    ``system`` messages are concatenated into the system prompt; everything else
    is concatenated (assistant turns are labelled) into the user prompt.
    """
    if isinstance(messages, bytes):
        return None, messages.decode("utf-8", "replace")
    if isinstance(messages, str):
        return None, messages
    if isinstance(messages, (LLMMessage, dict)):
        items: list[Any] = [messages]
    else:
        items = list(messages)

    system_parts: list[str] = []
    convo_parts: list[str] = []
    for item in items:
        role, content = _coerce_one(item)
        if not content:
            continue
        if role == "system":
            system_parts.append(content)
        elif role in {"user", "tool"}:
            convo_parts.append(content)
        else:  # assistant / unknown -> keep for context, labelled
            convo_parts.append(f"[{role}]\n{content}")

    system = "\n\n".join(system_parts) if system_parts else None
    user = "\n\n".join(convo_parts) if convo_parts else ""
    return system, user


def _resolve(messages: MessageLike, system: Optional[str]) -> tuple[Optional[str], str]:
    sys_from_msg, user = split_system_user(messages)
    return (system if system is not None else sys_from_msg), user


def _parse_output(stdout: str) -> str:
    """Extract the assistant text from ``claude -p --output-format json`` output."""
    text = (stdout or "").strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(data, dict):
        for key in ("result", "content", "text", "response"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return text
    if isinstance(data, list) and data:
        # stream-json transcripts: take the last textual chunk
        for entry in reversed(data):
            if isinstance(entry, dict):
                value = entry.get("result") or entry.get("text")
                if isinstance(value, str) and value.strip():
                    return value
    return text


# --------------------------------------------------------------------------- #
# Core invocation                                                              #
# --------------------------------------------------------------------------- #
def run_claude_sync(
    messages: MessageLike,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    cwd: Optional[Any] = None,
    timeout: Optional[float] = None,
    extra_args: Optional[Sequence[str]] = None,
) -> LLMResponse:
    """Run a single headless ``claude -p`` generation and return an ``LLMResponse``.

    Raises :class:`ClaudeUnavailableError` when the CLI is unavailable, times out,
    or exits non-zero — callers typically catch this and fall back to heuristics.
    """
    binary = claude_binary()
    if not binary:
        raise ClaudeUnavailableError(
            "`claude` CLI is unavailable (not installed or disabled via "
            f"{DISABLE_ENV}).",
        )

    system_text, user_text = _resolve(messages, system)
    if not user_text.strip():
        return LLMResponse(content="", model=model or "claude-code", finish_reason="empty")

    args: list[str] = [binary, "-p", user_text, "--output-format", "json"]
    if system_text:
        args += ["--append-system-prompt", system_text]
    chosen_model = model or os.getenv(MODEL_ENV)
    if chosen_model:
        args += ["--model", chosen_model]
    if extra_args:
        args += list(extra_args)

    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout or _default_timeout(),
            cwd=str(cwd) if cwd else None,
        )
    except subprocess.TimeoutExpired as exc:
        raise ClaudeUnavailableError(
            f"claude timed out after {timeout or _default_timeout()}s",
        ) from exc
    except OSError as exc:
        raise ClaudeUnavailableError(f"failed to launch claude: {exc}") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:500]
        raise ClaudeUnavailableError(f"claude exited {proc.returncode}: {detail}")

    content = _parse_output(proc.stdout)
    return LLMResponse(content=content, model=chosen_model or "claude-code", finish_reason="stop")


async def run_claude(
    messages: MessageLike,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    cwd: Optional[Any] = None,
    timeout: Optional[float] = None,
    extra_args: Optional[Sequence[str]] = None,
) -> LLMResponse:
    """Async wrapper around :func:`run_claude_sync` (runs in a worker thread)."""
    return await asyncio.to_thread(
        run_claude_sync,
        messages,
        system=system,
        model=model,
        cwd=cwd,
        timeout=timeout,
        extra_args=extra_args,
    )


# --------------------------------------------------------------------------- #
# Provider — drop-in replacement for the former LLMProvider implementations    #
# --------------------------------------------------------------------------- #
class ClaudeCodeProvider:
    """The single execution backend: the local Claude Code CLI.

    Duck-types the old ``LLMProvider`` interface plus the LangChain-ish
    ``invoke``/``ainvoke``/``complete`` helpers used across the codebase.
    """

    provider_name = "claude_code"

    def __init__(self, config: Any = None, *, model: Optional[str] = None, cwd: Optional[Any] = None, **_kwargs: Any):
        self._config = config
        self._model = model or getattr(config, "default_model", None) or None
        self._cwd = cwd

    # -- old LLMProvider surface -------------------------------------------- #
    def get_model_name(self, task_type: str = "default") -> str:
        return self._model or os.getenv(MODEL_ENV) or "claude-code"

    async def generate(
        self,
        messages: MessageLike,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[Sequence[Any]] = None,
        tool_choice: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        return await run_claude(
            messages,
            model=model or self._model,
            cwd=self._cwd,
            timeout=kwargs.get("timeout"),
        )

    async def stream(self, messages: MessageLike, model: Optional[str] = None, **kwargs: Any):
        response = await self.generate(messages, model=model, **kwargs)
        if response.content:
            yield response.content

    # -- LangChain-style helpers -------------------------------------------- #
    def invoke(self, messages: MessageLike, **kwargs: Any) -> LLMResponse:
        return run_claude_sync(messages, model=kwargs.get("model") or self._model, cwd=self._cwd)

    async def ainvoke(self, messages: MessageLike, **kwargs: Any) -> LLMResponse:
        return await run_claude(messages, model=kwargs.get("model") or self._model, cwd=self._cwd)

    def complete(self, messages: MessageLike, **kwargs: Any) -> str:
        return self.invoke(messages, **kwargs).content
