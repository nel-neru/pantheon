"""
Pantheon terminal-multiplexer runtime.

A Pantheon *session* maps to a multiplexer **workspace** (the "big tab") and each
agent in that session maps to a **surface** (the "small tab"). Surfaces are
created when an agent starts and closed when it finishes — fully automatically.

Drivers:
* :class:`~core.runtime.multiplexer.wmux_driver.WmuxDriver`     — Windows (wmux)
* :class:`~core.runtime.multiplexer.cmux_driver.CmuxDriver`     — macOS (cmux)
* :class:`~core.runtime.multiplexer.headless_driver.HeadlessDriver`
      — no GUI; runs each agent as a ``claude`` subprocess (the always-available
        substrate used in CI and when no multiplexer app is running).

Use :func:`get_driver` to obtain the right driver for the current machine.
"""

from __future__ import annotations

from core.runtime.multiplexer.base import (
    AgentSpec,
    MultiplexerDriver,
    MultiplexerUnavailableError,
    Surface,
    SurfaceStatus,
    Workspace,
)
from core.runtime.multiplexer.factory import get_driver

__all__ = [
    "AgentSpec",
    "MultiplexerDriver",
    "MultiplexerUnavailableError",
    "Surface",
    "SurfaceStatus",
    "Workspace",
    "get_driver",
]
