"""
Driver selection.

:func:`get_driver` returns the right :class:`MultiplexerDriver` for the current
machine:

* ``PANTHEON_MULTIPLEXER`` env forces a backend (``wmux`` / ``cmux`` /
  ``headless``) — used by tests and power users.
* Windows  -> :class:`WmuxDriver` when the wmux app is reachable.
* macOS    -> :class:`CmuxDriver` when a cmux endpoint is reachable.
* otherwise / when the GUI app is unavailable -> :class:`HeadlessDriver`, the
  always-works substrate that runs each agent as a ``claude`` subprocess.

The orchestrator can also force headless per-run; the GUI drivers degrade to
headless automatically when their app is not running, so a session always runs.
"""

from __future__ import annotations

import logging
import os
import platform
from typing import Optional

from core.runtime.multiplexer.base import MultiplexerDriver
from core.runtime.multiplexer.headless_driver import HeadlessDriver

logger = logging.getLogger(__name__)


def _make_wmux() -> Optional[MultiplexerDriver]:
    try:
        from core.runtime.multiplexer.wmux_driver import WmuxDriver

        drv = WmuxDriver()
        return drv if drv.is_available() else None
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("wmux driver unavailable: %s", exc)
        return None


def _make_cmux() -> Optional[MultiplexerDriver]:
    try:
        from core.runtime.multiplexer.cmux_driver import CmuxDriver

        drv = CmuxDriver()
        return drv if drv.is_available() else None
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("cmux driver unavailable: %s", exc)
        return None


def get_driver(
    prefer: Optional[str] = None, *, log_root: Optional[os.PathLike] = None
) -> MultiplexerDriver:
    """Return a driver. ``prefer`` (or ``PANTHEON_MULTIPLEXER``) forces a backend.

    Falls back to :class:`HeadlessDriver` whenever the GUI multiplexer is not
    available, so orchestration always has a working substrate.
    """
    choice = (prefer or os.getenv("PANTHEON_MULTIPLEXER") or "auto").lower()

    if choice == "headless":
        return HeadlessDriver(log_root=log_root)
    if choice == "wmux":
        return _make_wmux() or HeadlessDriver(log_root=log_root)
    if choice == "cmux":
        return _make_cmux() or HeadlessDriver(log_root=log_root)

    # auto
    system = platform.system()
    drv: Optional[MultiplexerDriver] = None
    if system == "Windows":
        drv = _make_wmux()
    elif system == "Darwin":
        drv = _make_cmux()
    if drv is not None:
        logger.info("Pantheon multiplexer: %s", drv.name)
        return drv
    logger.info("Pantheon multiplexer: headless (no GUI multiplexer detected)")
    return HeadlessDriver(log_root=log_root)
