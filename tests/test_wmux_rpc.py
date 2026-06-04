"""Tests for the wmux app-control RPC client against a fake wmux server."""

from __future__ import annotations

import json
import socket
import threading
from typing import Optional

import pytest

from core.runtime.multiplexer import wmux_rpc
from core.runtime.multiplexer.wmux_rpc import WmuxClient, WmuxNotConfirmedError


class FakeWmuxServer:
    """A minimal TCP server speaking the wmux control wire protocol."""

    def __init__(self, *, approved: bool = True):
        self.approved = approved
        self.received = []
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(8)
        self.port = self._srv.getsockname()[1]
        self._stop = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while not self._stop:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                break
            with conn:
                data = b""
                while b"\n" not in data:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                if not data:
                    continue
                req = json.loads(data.split(b"\n", 1)[0].decode("utf-8"))
                self.received.append(req)
                conn.sendall((json.dumps(self._respond(req)) + "\n").encode("utf-8"))

    def _respond(self, req):
        rid = req.get("id")
        method = req.get("method")
        if method in ("mcp.identify", "mcp.declarePermissions"):
            return {"id": rid, "ok": True, "result": {"identity": {"name": "pantheon"}}}
        if not self.approved:
            return {
                "id": rid, "ok": False,
                "error": f"{method}: awaiting user approval (promptId=abc-123)",
                "rejection": {"reason": "identity-status",
                              "pendingApproval": {"promptId": "abc-123"}},
            }
        if method == "workspace.list":
            return {"id": rid, "ok": True, "result": [{"id": "ws1", "name": "Work"}]}
        if method == "mcp.claimWorkspace":
            return {"id": rid, "ok": True,
                    "result": {"workspaceId": "ws-new", "ptyId": "pty-1",
                               "workspaceName": req["params"].get("name")}}
        return {"id": rid, "ok": True, "result": {"echo": method}}

    def close(self):
        self._stop = True
        try:
            self._srv.close()
        except OSError:
            pass


@pytest.fixture
def fake_server():
    srv = FakeWmuxServer()
    yield srv
    srv.close()


@pytest.fixture
def client_to(monkeypatch):
    def _make(srv: FakeWmuxServer) -> WmuxClient:
        monkeypatch.setattr(wmux_rpc, "read_auth_token", lambda: "test-token")
        monkeypatch.setattr(
            wmux_rpc, "resolve_endpoints",
            lambda: [("tcp", ("127.0.0.1", srv.port))],
        )
        monkeypatch.setattr(wmux_rpc, "_probe", lambda kind, target: True)
        return WmuxClient()
    return _make


def test_handshake_and_verify_when_approved(fake_server, client_to):
    client = client_to(fake_server)
    assert client.verify() is True
    methods = [r["method"] for r in fake_server.received]
    assert methods[:2] == ["mcp.identify", "mcp.declarePermissions"]
    assert "workspace.list" in methods
    # the envelope carries token + client identity
    assert fake_server.received[0]["token"] == "test-token"
    assert fake_server.received[0]["clientName"] == "pantheon"


def test_declare_permissions_payload(fake_server, client_to):
    client = client_to(fake_server)
    client.handshake()
    decl = next(r for r in fake_server.received if r["method"] == "mcp.declarePermissions")
    perms = decl["params"]["permissions"]
    assert "workspace.claim" in perms          # create a session workspace
    assert "pane.create" in perms              # add an agent surface
    assert "terminal.send" in perms            # type the claude command


def test_not_confirmed_raises(client_to):
    srv = FakeWmuxServer(approved=False)
    try:
        client = client_to(srv)
        with pytest.raises(WmuxNotConfirmedError) as ei:
            client.verify()
        assert ei.value.prompt_id == "abc-123"
    finally:
        srv.close()


def test_claim_workspace_roundtrip(fake_server, client_to):
    client = client_to(fake_server)
    res = client.call("mcp.claimWorkspace", {"name": "Session X"})
    assert res["workspaceId"] == "ws-new"
    assert res["ptyId"] == "pty-1"
    assert res["workspaceName"] == "Session X"
