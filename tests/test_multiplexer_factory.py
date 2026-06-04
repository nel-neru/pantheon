"""Driver selection / factory tests."""

from __future__ import annotations

import pytest

from core.runtime.multiplexer import get_driver
from core.runtime.multiplexer.headless_driver import HeadlessDriver
from core.runtime.multiplexer.wmux_driver import WmuxDriver, shell_command_for
from core.runtime.multiplexer.base import AgentSpec


def test_forced_headless():
    assert get_driver("headless").name == "headless"


def test_env_forces_headless(monkeypatch):
    monkeypatch.setenv("PANTHEON_MULTIPLEXER", "headless")
    assert get_driver().name == "headless"


def test_wmux_falls_back_to_headless_when_unavailable(monkeypatch):
    # Pretend wmux is not reachable -> factory must degrade to headless.
    monkeypatch.setattr(WmuxDriver, "is_available", lambda self: False)
    drv = get_driver("wmux")
    assert isinstance(drv, HeadlessDriver)


def test_shell_command_prefers_explicit():
    spec = AgentSpec(agent_id="a", title="A", command=["claude", "-p", "hi"],
                     shell_command="& claude -p (Get-Content x)")
    assert shell_command_for(spec) == "& claude -p (Get-Content x)"


def test_shell_command_quotes_argv():
    spec = AgentSpec(agent_id="a", title="A",
                     command=["claude", "-p", "two words", "--model", "x"])
    line = shell_command_for(spec)
    assert "'two words'" in line
    assert "--model x" in line
