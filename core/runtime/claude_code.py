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
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence, Union

from core.llm.base import LLMMessage, LLMResponse
from core.runtime.rate_limit import RateLimitInfo, detect_rate_limit
from core.runtime.usage_gate import RateLimitGate, gate_bypassed

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Configuration (env-driven, no secrets)                                       #
# --------------------------------------------------------------------------- #
DISABLE_ENV = "PANTHEON_NO_CLAUDE"  # truthy => behave as if claude is absent
BIN_ENV = "PANTHEON_CLAUDE_BIN"  # override path / name of the claude binary
MODEL_ENV = "PANTHEON_DEFAULT_MODEL"  # optional default model passed to --model
TIMEOUT_ENV = "PANTHEON_CLAUDE_TIMEOUT"  # seconds for a single headless call

# Fast-path: trim per-call cold-start for one-shot generations (no tools/MCP
# needed). Gated so it can be turned off, and the exact flags overridden once
# verified against the installed CLI version via ``claude --help``.
FAST_ENV = "PANTHEON_CLAUDE_FAST"  # truthy (default on) => add fast args
FAST_ARGS_ENV = "PANTHEON_CLAUDE_FAST_ARGS"  # whitespace-split override of the args
# Conservative default: suppress project MCP servers (the heaviest startup cost)
# regardless of cwd/settings. Only well-established flags here so an older CLI
# won't choke; richer flags (``--bare``, ``--disallowedTools``, ``--max-turns``)
# can be opted into via FAST_ARGS_ENV after verifying support.
_DEFAULT_FAST_ARGS = ("--strict-mcp-config", "--mcp-config", "{}")
# stderr signatures meaning "the CLI rejected our injected fast-path flags or
# their values" -> retry once without them. Covers both unknown-flag errors and
# problems specific to the default --mcp-config "{}" value, so the default fast
# path can never break generation on a CLI version that handles them differently.
_UNKNOWN_FLAG_SIGNALS = (
    "unknown option",
    "unknown argument",
    "unknown flag",
    "unexpected argument",
    "invalid option",
    "unrecognized",
    "unrecognised",
    "no such option",
    "strict-mcp-config",
    "mcp-config",
    "mcp config",
    "mcpservers",
)

# Per-call timing log (so slowness is measured, not guessed).
TIMING_LOG_ENV = "PANTHEON_CLAUDE_TIMING_LOG"  # path override; "" / "off" disables

_TRUTHY = {"1", "true", "yes", "on"}


class ClaudeUnavailableError(RuntimeError):
    """Raised when the ``claude`` CLI cannot be used for a generation call."""


class ClaudeRateLimitedError(ClaudeUnavailableError):
    """Raised when generation is blocked by a Claude usage/rate limit.

    Subclasses :class:`ClaudeUnavailableError` so every existing
    ``except ClaudeUnavailableError`` fallback keeps working; callers that
    care about the limit specifically can catch this type and read ``info``.
    The message embeds the reset time as an ISO timestamp so legacy callers
    that re-run :func:`detect_rate_limit` over ``str(exc)`` recover it.
    """

    def __init__(self, message: str, info: Optional[RateLimitInfo] = None):
        super().__init__(message)
        self.info = info or RateLimitInfo(limited=True)


def _limit_message(info: RateLimitInfo) -> str:
    reset = info.reset_at.isoformat() if info.reset_at else "unknown"
    base = f"claude usage limit reached (scope={info.scope}); resets at {reset}"
    return f"{base}. {info.message}".strip() if info.message else base


def _default_timeout() -> float:
    try:
        return float(os.getenv(TIMEOUT_ENV, "180"))
    except (TypeError, ValueError):
        return 180.0


def _fast_enabled() -> bool:
    """Whether to add one-shot fast-path args (default on)."""
    return os.getenv(FAST_ENV, "1").strip().lower() in _TRUTHY


def _fast_args() -> list[str]:
    """The extra argv injected for one-shot generations (overridable via env)."""
    if not _fast_enabled():
        return []
    override = os.getenv(FAST_ARGS_ENV)
    if override is not None:
        return override.split()
    return list(_DEFAULT_FAST_ARGS)


def _looks_like_flag_error(stderr: str) -> bool:
    low = (stderr or "").lower()
    return any(sig in low for sig in _UNKNOWN_FLAG_SIGNALS)


def _timing_log_path() -> Optional[str]:
    """Resolve the per-call timing log path, or ``None`` when disabled."""
    override = os.getenv(TIMING_LOG_ENV)
    if override is not None:
        override = override.strip()
        if override == "" or override.lower() in {"off", "0", "none", "false"}:
            return None
        return override
    # Default: alongside the global platform state (~/.pantheon).
    try:
        from core.platform.state import get_platform_home

        return str(Path(get_platform_home()) / "claude_calls.jsonl")
    except Exception:  # pragma: no cover - platform state optional
        return None


def _log_call_timing(
    *,
    elapsed_ms: int,
    model: Optional[str],
    prompt_chars: int,
    system_chars: int,
    returncode: Optional[int],
    timed_out: bool,
    fast: bool,
) -> None:
    """Append one JSONL record of a real ``claude`` call's wall-clock time.

    Best-effort: never let logging failures affect the generation result.
    """
    path = _timing_log_path()
    if not path:
        return
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "elapsed_ms": elapsed_ms,
        "model": model or "claude-code",
        "prompt_chars": prompt_chars,
        "system_chars": system_chars,
        "returncode": returncode,
        "timed_out": timed_out,
        "fast": fast,
    }
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:  # pragma: no cover - logging must not break calls
        logger.debug("failed to write claude timing log: %s", exc)


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


def _parse_result(stdout: str) -> tuple[str, bool]:
    """Extract ``(assistant_text, is_error)`` from ``claude -p --output-format json`` output."""
    text = (stdout or "").strip()
    if not text:
        return "", False
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text, False
    if isinstance(data, dict):
        is_error = bool(data.get("is_error"))
        for key in ("result", "content", "text", "response"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value, is_error
        return text, is_error
    if isinstance(data, list) and data:
        # stream-json transcripts: take the last textual chunk
        for entry in reversed(data):
            if isinstance(entry, dict):
                value = entry.get("result") or entry.get("text")
                if isinstance(value, str) and value.strip():
                    return value, bool(entry.get("is_error"))
    return text, False


def _parse_output(stdout: str) -> str:
    """Extract the assistant text from ``claude -p --output-format json`` output."""
    return _parse_result(stdout)[0]


# 成功（exit 0）出力に対するレート制限検知は誤検知対策として「結果 JSON が
# is_error=true」または「短い結果テキスト」に限定する。CLI の制限メッセージは
# 常に短い 1〜2 行で返る一方、正常な長文生成が "rate limit" 等に言及しただけで
# 全 daemon を一斉 pause させるわけにはいかない。
_SUCCESS_SCAN_MAX_CHARS = 400


def _detect_success_rate_limit(content: str, is_error: bool) -> Optional[RateLimitInfo]:
    if not content:
        return None
    if not is_error and len(content) > _SUCCESS_SCAN_MAX_CHARS:
        return None
    info = detect_rate_limit(content)
    return info if info.limited else None


# --------------------------------------------------------------------------- #
# Core invocation                                                              #
# --------------------------------------------------------------------------- #
def _build_cli_args(
    binary: str,
    user_text: str,
    system_text: Optional[str],
    chosen_model: Optional[str],
    *,
    fast: bool = True,
    extra_args: Optional[Sequence[str]] = None,
) -> list[str]:
    """Assemble the argv for a one-shot headless ``claude -p`` call.

    ``fast`` injects :func:`_fast_args` (cold-start trimming for one-shot
    generations that need no tools/MCP). Pure/deterministic so it is unit-tested
    directly without spawning the CLI.
    """
    args: list[str] = [binary, "-p", user_text, "--output-format", "json"]
    if system_text:
        args += ["--append-system-prompt", system_text]
    if chosen_model:
        args += ["--model", chosen_model]
    if fast:
        args += _fast_args()
    if extra_args:
        args += list(extra_args)
    return args


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
    Raises :class:`ClaudeRateLimitedError` (a subclass) when a usage/rate limit
    is active or newly detected; the limit is shared cross-process via
    :class:`RateLimitGate` so no further CLI processes are spawned (and no
    tokens wasted) until the window reopens.
    """
    binary = claude_binary()
    if not binary:
        raise ClaudeUnavailableError(
            f"`claude` CLI is unavailable (not installed or disabled via {DISABLE_ENV}).",
        )

    gate = RateLimitGate()
    if not gate_bypassed():
        active = gate.current()
        if active is not None:
            raise ClaudeRateLimitedError(_limit_message(active), active)

    system_text, user_text = _resolve(messages, system)
    if not user_text.strip():
        return LLMResponse(content="", model=model or "claude-code", finish_reason="empty")

    chosen_model = model or os.getenv(MODEL_ENV)
    effective_timeout = timeout or _default_timeout()
    prompt_chars = len(user_text)
    system_chars = len(system_text or "")

    def _invoke(use_fast: bool) -> subprocess.CompletedProcess:
        cli_args = _build_cli_args(
            binary,
            user_text,
            system_text,
            chosen_model,
            fast=use_fast,
            extra_args=extra_args,
        )
        return subprocess.run(
            cli_args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=effective_timeout,
            cwd=str(cwd) if cwd else None,
        )

    fast = bool(_fast_args())
    started = time.monotonic()
    timed_out = False
    proc: Optional[subprocess.CompletedProcess] = None
    try:
        try:
            proc = _invoke(fast)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            raise ClaudeUnavailableError(
                f"claude timed out after {effective_timeout}s",
            ) from exc
        except OSError as exc:
            raise ClaudeUnavailableError(f"failed to launch claude: {exc}") from exc

        # If the installed CLI rejects one of our fast-path flags, retry once
        # without them so a version mismatch never breaks generation outright.
        if fast and proc.returncode != 0 and _looks_like_flag_error(proc.stderr or ""):
            logger.warning(
                "claude rejected fast-path flags (%s); retrying without them. "
                "Set %s to override the flags or %s=0 to disable.",
                (proc.stderr or "").strip()[:200],
                FAST_ARGS_ENV,
                FAST_ENV,
            )
            fast = False
            try:
                proc = _invoke(False)
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                raise ClaudeUnavailableError(
                    f"claude timed out after {effective_timeout}s",
                ) from exc
            except OSError as exc:
                raise ClaudeUnavailableError(f"failed to launch claude: {exc}") from exc
    finally:
        _log_call_timing(
            elapsed_ms=int((time.monotonic() - started) * 1000),
            model=chosen_model,
            prompt_chars=prompt_chars,
            system_chars=system_chars,
            returncode=(proc.returncode if proc is not None else None),
            timed_out=timed_out,
            fast=fast,
        )

    if proc.returncode != 0:
        combined = "\n".join(part for part in (proc.stderr, proc.stdout) if part)
        info = detect_rate_limit(combined)
        if info.limited:
            gate.report(info)
            raise ClaudeRateLimitedError(_limit_message(info), info)
        detail = (proc.stderr or proc.stdout or "").strip()[:500]
        raise ClaudeUnavailableError(f"claude exited {proc.returncode}: {detail}")

    content, is_error = _parse_result(proc.stdout)
    # CLI はレート制限を「正常終了 (exit 0) の結果テキスト」として返すことがある。
    info = _detect_success_rate_limit(content, is_error)
    if info is not None:
        gate.report(info)
        raise ClaudeRateLimitedError(_limit_message(info), info)
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

    def __init__(
        self,
        config: Any = None,
        *,
        model: Optional[str] = None,
        cwd: Optional[Any] = None,
        **_kwargs: Any,
    ):
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
