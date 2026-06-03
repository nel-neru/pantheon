"""UpdateHub のブロードキャストテスト（F11）。

接続管理・全接続への配信・送信失敗した接続(stale)の自動除去を固定する。
"""

from __future__ import annotations

from typing import Any, List

from web.server import UpdateHub


class _FakeWS:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: List[Any] = []
        self.accepted = False
        self.closed = False
        self.close_code: int | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000) -> None:
        self.closed = True
        self.close_code = code

    async def send_json(self, event: Any) -> None:
        if self.fail:
            raise RuntimeError("connection dead")
        self.sent.append(event)


async def test_connect_accepts_and_registers():
    hub = UpdateHub()
    ws = _FakeWS()
    assert await hub.connect(ws) is True
    assert ws.accepted is True
    assert ws in hub._connections


async def test_connect_rejects_when_at_capacity():
    hub = UpdateHub(max_connections=2)
    a, b = _FakeWS(), _FakeWS()
    assert await hub.connect(a) is True
    assert await hub.connect(b) is True
    c = _FakeWS()
    assert await hub.connect(c) is False  # 上限超過は拒否（A9）
    assert c.closed is True and c.close_code == 1013
    assert c not in hub._connections


async def test_zero_max_connections_is_unlimited():
    hub = UpdateHub(max_connections=0)
    for _ in range(5):
        assert await hub.connect(_FakeWS()) is True
    assert len(hub._connections) == 5


async def test_broadcast_delivers_to_all_live_connections():
    hub = UpdateHub()
    a, b = _FakeWS(), _FakeWS()
    await hub.connect(a)
    await hub.connect(b)
    await hub.broadcast({"type": "ping", "n": 1})
    assert a.sent == [{"type": "ping", "n": 1}]
    assert b.sent == [{"type": "ping", "n": 1}]


async def test_broadcast_removes_stale_connections():
    hub = UpdateHub()
    good, dead = _FakeWS(), _FakeWS(fail=True)
    await hub.connect(good)
    await hub.connect(dead)
    await hub.broadcast({"type": "x"})
    assert good.sent == [{"type": "x"}]
    assert dead not in hub._connections  # 送信失敗で除去
    assert good in hub._connections


async def test_disconnect_removes_connection():
    hub = UpdateHub()
    ws = _FakeWS()
    await hub.connect(ws)
    await hub.disconnect(ws)
    assert ws not in hub._connections
    # 接続ゼロでも broadcast は例外を出さない
    await hub.broadcast({"type": "noop"})
