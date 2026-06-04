"""
Low-level JSON-RPC client for the **wmux app control endpoint**.

wmux (the native Windows terminal multiplexer for AI agents) exposes a local
JSON-RPC control endpoint that the running Electron app serves. This is the
surface that external plugins (Claude Code's wmux MCP, and Pantheon) use to
list/create workspaces, split panes, drive terminals and poll lifecycle
events. The wire protocol — reverse-engineered from the bundled app +
mcp-bundle — is one newline-delimited JSON envelope per request::

    {"id": "<uuid>", "method": "<m>", "params": {...},
     "token": "<auth>", "clientName": "pantheon", "clientVersion": "1.0"}\\n

and a single newline-terminated JSON response::

    {"id": "<uuid>", "ok": true,  "result": <any>}\\n
    {"id": "<uuid>", "ok": false, "error": "<message>"}\\n

Transport (Windows):
    * primary  : TCP ``127.0.0.1:<port>`` where ``port`` is read from
                 ``~/.wmux-tcp-port``.
    * fallback : named pipe ``\\\\.\\pipe\\wmux-<username>``.
    * override : ``WMUX_SOCKET_PATH`` (named pipe / unix socket path).
Auth token  : ``~/.wmux-auth-token`` (or the ``WMUX_AUTH_TOKEN`` env var).

NOTE: this is a *different* endpoint from the daemon pipe
(``~/.wmux/daemon-pipe`` / ``daemon-auth-token``), which only exposes the flat
``daemon.*`` PTY methods. The app control endpoint proxies those too, plus the
whole ``workspace.* / surface.* / pane.* / input.* / events.* / mcp.*`` surface.

Capability model: the app gates methods behind declared capabilities. A plugin
must first ``mcp.identify`` then ``mcp.declarePermissions``; the first time a
new plugin name declares permissions the user approves it once in the wmux GUI
(trust persisted to ``~/.wmux/plugin-trust.json``). After that the handshake is
silent. :class:`WmuxClient` performs this handshake lazily.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CLIENT_NAME = "pantheon"
CLIENT_VERSION = "1.0"

#: Capabilities Pantheon needs, mapped from the methods it calls. Declaring a
#: bare capability (no glob) grants unrestricted access to it.
DEFAULT_PERMISSIONS: Tuple[str, ...] = (
    "workspace.claim",    # mcp.claimWorkspace  -> create a session workspace
    "workspace.read",     # workspace.list / workspace.current
    "pane.read",          # pane.list / pane.focus
    "pane.create",        # pane.split          -> add an agent surface
    "pane.search",        # pane.search
    "meta.read",          # pane.getMetadata
    "meta.write",         # pane.setMetadata / meta.setStatus
    "events.subscribe",   # events.poll
    "terminal.send",      # input.send / input.sendKey
    "terminal.read",      # input.readScreen / terminal.readEvents
)

_RATIONALE = "Pantheon — AI agent organization orchestrator (sessions=workspaces, agents=panes)."

_CONNECT_TIMEOUT = 10.0
_RETRIES = 3
_RETRY_DELAY = 0.4


class WmuxRpcError(RuntimeError):
    """A wmux RPC call returned an error or could not be completed."""


class WmuxUnavailableError(WmuxRpcError):
    """The wmux app control endpoint could not be reached (app not running)."""


class WmuxNotConfirmedError(WmuxRpcError):
    """The plugin is not yet trusted — the user must approve it once in wmux."""

    def __init__(self, message: str, prompt_id: Optional[str] = None):
        super().__init__(message)
        self.prompt_id = prompt_id


# --------------------------------------------------------------------------- #
# Endpoint / auth resolution
# --------------------------------------------------------------------------- #
def _home() -> Path:
    return Path(os.getenv("USERPROFILE") or os.getenv("HOME") or str(Path.home()))


def read_auth_token() -> Optional[str]:
    env = os.getenv("WMUX_AUTH_TOKEN")
    if env and env.strip():
        return env.strip()
    try:
        token = (_home() / ".wmux-auth-token").read_text(encoding="utf-8").strip()
        return token or None
    except OSError:
        return None


def _tcp_port() -> Optional[int]:
    try:
        raw = (_home() / ".wmux-tcp-port").read_text(encoding="utf-8").strip()
        return int(raw) if raw else None
    except (OSError, ValueError):
        return None


def _default_pipe_name() -> str:
    user = os.getenv("USERNAME") or os.getenv("USER") or "default"
    return rf"\\.\pipe\wmux-{user}"


def resolve_endpoints() -> List[Tuple[str, Any]]:
    """Ordered list of control endpoints to try: ``("tcp", (host, port))`` or
    ``("pipe", path)``."""
    endpoints: List[Tuple[str, Any]] = []
    override = os.getenv("WMUX_SOCKET_PATH")
    if override:
        endpoints.append(("pipe", override))
    port = _tcp_port()
    if os.name == "nt" and port:
        endpoints.append(("tcp", ("127.0.0.1", port)))
    if os.name == "nt":
        endpoints.append(("pipe", _default_pipe_name()))
    else:
        # POSIX (for cmux-style hosts / tests): unix socket under ~/.wmux.sock
        endpoints.append(("pipe", str(_home() / ".wmux.sock")))
        if port:
            endpoints.append(("tcp", ("127.0.0.1", port)))
    return endpoints


def is_wmux_running() -> bool:
    """Best-effort: an auth token exists and a control endpoint is reachable."""
    if not read_auth_token():
        return False
    for kind, target in resolve_endpoints():
        if _probe(kind, target):
            return True
    return False


def _probe(kind: str, target: Any) -> bool:
    try:
        if kind == "tcp":
            with socket.create_connection(target, timeout=1.0):
                return True
        else:
            # named pipe / unix socket: opening it is the probe
            fh = open(target, "r+b", buffering=0)
            fh.close()
            return True
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# Wire transport
# --------------------------------------------------------------------------- #
def _read_line_socket(sock: socket.socket) -> bytes:
    buf = bytearray()
    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    return bytes(buf).split(b"\n", 1)[0]


def _read_line_pipe(fh) -> bytes:
    chunks = bytearray()
    while True:
        b = fh.read(1)
        if not b or b == b"\n":
            break
        chunks += b
    return bytes(chunks)


def _send_once(kind: str, target: Any, payload: bytes, timeout: float) -> bytes:
    if kind == "tcp":
        sock = socket.create_connection(target, timeout=timeout)
        try:
            sock.settimeout(timeout)
            sock.sendall(payload)
            return _read_line_socket(sock)
        finally:
            sock.close()
    else:
        with open(target, "r+b", buffering=0) as fh:
            fh.write(payload)
            try:
                fh.flush()
            except OSError:
                pass
            return _read_line_pipe(fh)


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
class WmuxClient:
    """Stateful client for the wmux app control endpoint.

    Resolves a working endpoint, performs the ``identify`` + ``declarePermissions``
    handshake lazily/once, and exposes :meth:`call` for arbitrary RPC methods.
    """

    def __init__(
        self,
        name: str = CLIENT_NAME,
        version: str = CLIENT_VERSION,
        permissions: Tuple[str, ...] = DEFAULT_PERMISSIONS,
        *,
        timeout: float = _CONNECT_TIMEOUT,
    ):
        self.name = name
        self.version = version
        self.permissions = list(permissions)
        self.timeout = timeout
        self._endpoint: Optional[Tuple[str, Any]] = None
        self._handshaked = False

    # -- low level ---------------------------------------------------------- #
    def _resolve_endpoint(self) -> Tuple[str, Any]:
        if self._endpoint is not None:
            return self._endpoint
        endpoints = resolve_endpoints()
        if not endpoints:
            raise WmuxUnavailableError("no wmux control endpoint could be resolved")
        last: Optional[Exception] = None
        for kind, target in endpoints:
            if _probe(kind, target):
                self._endpoint = (kind, target)
                return self._endpoint
            last = WmuxUnavailableError(f"{kind} {target!r} not reachable")
        raise WmuxUnavailableError(f"wmux app is not running ({last})")

    def _raw_call(self, method: str, params: Optional[Dict[str, Any]]) -> Any:
        token = read_auth_token()
        if not token:
            raise WmuxUnavailableError("wmux auth token not found — is the wmux app running?")
        kind, target = self._resolve_endpoint()
        envelope = {
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params or {},
            "token": token,
            "clientName": self.name,
            "clientVersion": self.version,
        }
        payload = (json.dumps(envelope) + "\n").encode("utf-8")

        last: Optional[Exception] = None
        for attempt in range(_RETRIES):
            try:
                raw = _send_once(kind, target, payload, self.timeout)
                if not raw:
                    raise WmuxRpcError(f"empty response for {method}")
                resp = json.loads(raw.decode("utf-8", "replace"))
                if not isinstance(resp, dict):
                    return resp
                if resp.get("ok"):
                    return resp.get("result")
                # ok == false -> error path
                err = str(resp.get("error") or "unknown error")
                rejection = resp.get("rejection") or {}
                if "unconfirmed" in err or rejection.get("status") == "unconfirmed":
                    raise WmuxNotConfirmedError(err)
                if "awaiting user approval" in err:
                    prompt = (rejection.get("pendingApproval") or {}).get("promptId")
                    raise WmuxNotConfirmedError(err, prompt_id=prompt)
                raise WmuxRpcError(f"{method}: {err}")
            except WmuxNotConfirmedError:
                raise
            except (FileNotFoundError, ConnectionError) as exc:
                # endpoint went away — re-resolve once
                self._endpoint = None
                last = WmuxUnavailableError(str(exc))
                try:
                    kind, target = self._resolve_endpoint()
                except WmuxUnavailableError as e:
                    raise e
                time.sleep(_RETRY_DELAY)
            except OSError as exc:
                last = exc
                time.sleep(_RETRY_DELAY)
            except json.JSONDecodeError as exc:
                raise WmuxRpcError(f"invalid JSON from wmux for {method}: {exc}") from exc
        raise WmuxRpcError(f"wmux RPC failed for {method}: {last}")

    # -- handshake ---------------------------------------------------------- #
    def identify(self) -> Any:
        return self._raw_call("mcp.identify", {"name": self.name, "version": self.version})

    def declare_permissions(self) -> Any:
        return self._raw_call(
            "mcp.declarePermissions",
            {"permissions": self.permissions, "rationale": _RATIONALE},
        )

    def handshake(self, force: bool = False) -> None:
        """Perform identify + declarePermissions.

        These two methods always succeed (they merely register Pantheon and its
        requested capabilities). The *enforcement* of approval happens on the
        first capability-gated call — use :meth:`verify` to surface that.
        """
        if self._handshaked and not force:
            return
        self.identify()
        self.declare_permissions()
        self._handshaked = True

    def verify(self) -> bool:
        """Confirm the plugin is approved by making a gated read call.

        Raises :class:`WmuxNotConfirmedError` (with ``prompt_id``) when the user
        still has to approve Pantheon once in the wmux GUI.
        """
        self.handshake()
        self._raw_call("workspace.list", None)  # gated by workspace.read
        return True

    # -- public ------------------------------------------------------------- #
    def call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Call an RPC method, handshaking first if needed."""
        if not self._handshaked and not method.startswith("mcp."):
            self.handshake()
        return self._raw_call(method, params)

    def available(self) -> bool:
        try:
            self._resolve_endpoint()
            return read_auth_token() is not None
        except WmuxUnavailableError:
            return False


# --------------------------------------------------------------------------- #
# Module-level convenience (single shared client)
# --------------------------------------------------------------------------- #
_shared: Optional[WmuxClient] = None


def get_client() -> WmuxClient:
    global _shared
    if _shared is None:
        _shared = WmuxClient()
    return _shared


def call(method: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """Convenience one-shot call via the shared client."""
    return get_client().call(method, params)
