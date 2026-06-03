"""
Pytest configuration for Pantheon.

Pantheon's only execution backend is the local ``claude`` CLI (Claude Code).
Tests must stay deterministic and fully offline, so we disable the CLI for the
entire test session: ``core.runtime.claude_code.claude_available()`` returns
False, every generation call raises ``ClaudeUnavailableError``, and each agent
falls back to its built-in heuristic path — exactly the behaviour the suite was
written against. A test that specifically exercises the Claude Code backend can
opt back in by monkeypatching the binary resolver.
"""

from __future__ import annotations

import os

os.environ.setdefault("PANTHEON_NO_CLAUDE", "1")
