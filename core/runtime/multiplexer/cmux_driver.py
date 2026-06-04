"""
cmux multiplexer driver (macOS).

cmux is the macOS sibling of wmux and exposes a compatible app control
endpoint. This driver reuses the wmux driving logic verbatim, pointing the RPC
client at cmux's socket/token (``WMUX_SOCKET_PATH`` / ``WMUX_AUTH_TOKEN`` are
honoured, falling back to ``~/.cmux.sock`` + ``~/.cmux-auth-token``).

Windows (wmux) is the fully-exercised backend; on macOS this driver is wired
the same way but, until validated against a live cmux, :meth:`is_available`
only reports ready when a cmux endpoint is actually reachable — otherwise the
factory falls back to the headless substrate so orchestration always works.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from core.runtime.multiplexer.wmux_driver import WmuxDriver
from core.runtime.multiplexer.wmux_rpc import WmuxClient


def _cmux_client() -> WmuxClient:
    # Reuse the wmux wire client; allow cmux-specific socket/token via env.
    home = Path(os.getenv("HOME") or str(Path.home()))
    os.environ.setdefault("WMUX_SOCKET_PATH", str(home / ".cmux.sock"))
    if not os.getenv("WMUX_AUTH_TOKEN"):
        token_file = home / ".cmux-auth-token"
        try:
            os.environ["WMUX_AUTH_TOKEN"] = token_file.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return WmuxClient(name="pantheon")


class CmuxDriver(WmuxDriver):
    name = "cmux"

    def __init__(self, client: Optional[WmuxClient] = None):
        super().__init__(client or _cmux_client())
