"""
Pantheon runtime — Claude Code execution backend and terminal-multiplexer
orchestration (wmux / cmux).

This package replaces the former multi-provider LLM API layer. Pantheon does not
talk to any hosted LLM API: all reasoning happens through the local `claude` CLI
(Claude Code), and agents are run inside terminal-multiplexer surfaces.
"""

from __future__ import annotations

from core.runtime.claude_code import (
    ClaudeCodeProvider,
    ClaudeUnavailableError,
    claude_available,
    claude_binary,
    run_claude,
    run_claude_sync,
)

__all__ = [
    "ClaudeCodeProvider",
    "ClaudeUnavailableError",
    "claude_available",
    "claude_binary",
    "run_claude",
    "run_claude_sync",
]
