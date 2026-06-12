"""X アダプタの実投稿（assisted ハンドオフ）のテスト — 実ブラウザは起動しない。

web intent URL に本文をプリフィルして人間に最終送信を引き渡すフロー論理を
フェイク注入で検証する。
"""

from __future__ import annotations

import json
from urllib.parse import quote

import core.publishing.adapters.handoff as handoff_mod
from core.publishing.adapters.x import (
    X_COMPOSE_INTENT_URL,
    X_POST_CHAR_LIMIT,
    XPublisher,
)
from core.publishing.base import PublishContent, PublishTarget
from core.publishing.session import SessionStore


class _FakePage:
    def __init__(self) -> None:
        self.goto_urls: list[str] = []
        self.goto_error: Exception | None = None

    async def goto(self, url: str) -> None:
        if self.goto_error is not None:
            raise self.goto_error
        self.goto_urls.append(url)


class _FakeContext:
    def __init__(self, page: _FakePage) -> None:
        self._page = page

    async def new_page(self) -> _FakePage:
        return self._page


class _FakeLauncher:
    def __init__(self, page: _FakePage) -> None:
        self._page = page
        self.closed = False

    async def launch(self) -> _FakeContext:
        return _FakeContext(self._page)

    async def close(self) -> None:
        self.closed = True


def _connected_store(tmp_path) -> SessionStore:
    store = SessionStore(platform_home=tmp_path)
    store.ensure_dir("x")
    store.state_path("x").write_text(json.dumps({"cookies": []}), encoding="utf-8")
    return store


def _target(mode: str = "assisted") -> PublishTarget:
    return PublishTarget(platform="x", mode=mode)


async def test_auto_mode_is_not_implemented_yet(tmp_path):
    publisher = XPublisher(session_store=_connected_store(tmp_path))
    result = await publisher._publish_live(PublishContent(body="t"), _target(mode="auto"))
    assert result.ok is False
    assert "auto" in result.error and "未実装" in result.error


async def test_not_connected_fails_with_connect_hint(tmp_path):
    factory_calls: list[int] = []
    publisher = XPublisher(
        session_store=SessionStore(platform_home=tmp_path),
        launcher_factory=lambda: factory_calls.append(1),
    )
    result = await publisher._publish_live(PublishContent(body="t"), _target())
    assert result.ok is False
    assert "pantheon publish connect x" in result.error
    assert factory_calls == []


async def test_empty_text_fails_without_launching_browser(tmp_path):
    factory_calls: list[int] = []
    publisher = XPublisher(
        session_store=_connected_store(tmp_path),
        launcher_factory=lambda: factory_calls.append(1),
    )
    result = await publisher._publish_live(PublishContent(title="", body="  "), _target())
    assert result.ok is False
    assert "空" in result.error
    assert factory_calls == []


async def test_assisted_prefills_intent_url_and_hands_off(tmp_path, monkeypatch):
    monkeypatch.setattr(handoff_mod, "_HANDOFF_KEEPALIVE", [])
    page = _FakePage()
    launcher = _FakeLauncher(page)
    publisher = XPublisher(
        session_store=_connected_store(tmp_path), launcher_factory=lambda: launcher
    )
    body = "今日の学び #pantheon"

    result = await publisher._publish_live(PublishContent(body=body), _target())

    assert result.ok is True
    assert result.handed_off is True
    assert page.goto_urls == [f"{X_COMPOSE_INTENT_URL}?text={quote(body)}"]
    assert launcher.closed is False  # 最終送信は人間 — ブラウザは開いたまま
    assert handoff_mod._HANDOFF_KEEPALIVE == [launcher]


async def test_body_missing_falls_back_to_title(tmp_path, monkeypatch):
    monkeypatch.setattr(handoff_mod, "_HANDOFF_KEEPALIVE", [])
    page = _FakePage()
    publisher = XPublisher(
        session_store=_connected_store(tmp_path),
        launcher_factory=lambda: _FakeLauncher(page),
    )
    result = await publisher._publish_live(PublishContent(title="タイトルのみ"), _target())
    assert result.ok is True
    assert page.goto_urls == [f"{X_COMPOSE_INTENT_URL}?text={quote('タイトルのみ')}"]


async def test_over_limit_text_warns_in_detail(tmp_path, monkeypatch):
    monkeypatch.setattr(handoff_mod, "_HANDOFF_KEEPALIVE", [])
    long_body = "あ" * (X_POST_CHAR_LIMIT + 1)
    publisher = XPublisher(
        session_store=_connected_store(tmp_path),
        launcher_factory=lambda: _FakeLauncher(_FakePage()),
    )
    result = await publisher._publish_live(PublishContent(body=long_body), _target())
    assert result.ok is True and result.handed_off is True
    assert "超えています" in result.detail  # 正直に警告（自動分割は Phase 2）


async def test_handoff_keepalive_contract(monkeypatch):
    """共有 keepalive の直接契約: 生存は残す・死んだものは close して除く・無印は生存扱い。"""

    class _Stub:
        def __init__(self, alive: bool | None):
            self._alive = alive
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class _Dead(_Stub):
        def is_alive(self) -> bool:
            return False

    class _Live(_Stub):
        def is_alive(self) -> bool:
            return True

    dead, live, plain = _Dead(False), _Live(True), _Stub(None)  # plain は is_alive 無し
    monkeypatch.setattr(handoff_mod, "_HANDOFF_KEEPALIVE", [])
    for item in (dead, live, plain):
        handoff_mod.keep_alive(item)

    await handoff_mod.prune_handoff_keepalive()

    assert handoff_mod._HANDOFF_KEEPALIVE == [live, plain]
    assert dead.closed is True and live.closed is False and plain.closed is False


async def test_goto_failure_closes_browser_and_is_honest(tmp_path, monkeypatch):
    monkeypatch.setattr(handoff_mod, "_HANDOFF_KEEPALIVE", [])
    page = _FakePage()
    page.goto_error = RuntimeError("net::ERR_INTERNET_DISCONNECTED")
    launcher = _FakeLauncher(page)
    publisher = XPublisher(
        session_store=_connected_store(tmp_path), launcher_factory=lambda: launcher
    )

    result = await publisher._publish_live(PublishContent(body="t"), _target())

    assert result.ok is False
    assert "起動に失敗" in result.error
    assert launcher.closed is True
    assert handoff_mod._HANDOFF_KEEPALIVE == []
