"""WordPress アダプタの実投稿（assisted ハンドオフ）のテスト — 実ブラウザは起動しない。

フェイク launcher/page を注入してフロー論理（サイトURL/接続/空コンテンツのチェック→
エディタ起動→タイトル流し込み best-effort→ブラウザを開いたままハンドオフ）を検証する。
WordPress の live 経路はこれまで未テストだったため、空コンテンツ・ガード追加（Cycle 36）と
あわせて基本フローも固定する。
"""

from __future__ import annotations

import json

import core.publishing.adapters.handoff as handoff_mod
from core.publishing.adapters.wordpress import (
    WP_ADMIN_NEW_POST_PATH,
    WP_TITLE_SELECTOR,
    WordPressPublisher,
)
from core.publishing.base import PublishContent, PublishTarget
from core.publishing.session import SessionStore


class _FakePage:
    def __init__(self) -> None:
        self.goto_urls: list[str] = []
        self.waited: list[str] = []
        self.filled: dict[str, str] = {}

    async def goto(self, url: str) -> None:
        self.goto_urls.append(url)

    async def wait_for_selector(self, selector: str, timeout: int | None = None) -> None:
        self.waited.append(selector)

    async def fill(self, selector: str, value: str) -> None:
        self.filled[selector] = value


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
    store.ensure_dir("wordpress")
    store.state_path("wordpress").write_text(json.dumps({"cookies": []}), encoding="utf-8")
    return store


def _target(account: str = "https://example.com") -> PublishTarget:
    return PublishTarget(platform="wordpress", account=account, mode="assisted")


def _content() -> PublishContent:
    return PublishContent(title="記事タイトル", body="本文")


async def test_auto_mode_is_not_implemented_yet(tmp_path):
    # mode=auto は Phase 2 未実装で弾く（auto チェックは _publish_live の最初＝ブラウザ起動前に return）。
    publisher = WordPressPublisher(session_store=_connected_store(tmp_path))
    result = await publisher._publish_live(
        _content(), PublishTarget(platform="wordpress", account="https://example.com", mode="auto")
    )
    assert result.ok is False
    assert "auto" in result.error and "未実装" in result.error


async def test_missing_site_url_fails(tmp_path):
    publisher = WordPressPublisher(session_store=_connected_store(tmp_path))
    result = await publisher._publish_live(_content(), _target(account=""))
    assert result.ok is False
    assert "サイトURL" in result.error


async def test_not_connected_fails_with_connect_hint(tmp_path):
    factory_calls: list[int] = []
    publisher = WordPressPublisher(
        session_store=SessionStore(platform_home=tmp_path),
        launcher_factory=lambda: factory_calls.append(1),
    )
    result = await publisher._publish_live(_content(), _target())
    assert result.ok is False
    assert "pantheon publish connect wordpress" in result.error
    assert factory_calls == []  # 未接続ならブラウザを起動しない


async def test_empty_content_fails_without_launching_browser(tmp_path):
    # サイトURL・接続が揃っていても空の下書きはブラウザを起動せず ok=False で弾く
    # （X / note と同契約・preview≥live の honesty を一様化）。
    factory_calls: list[int] = []
    publisher = WordPressPublisher(
        session_store=_connected_store(tmp_path),
        launcher_factory=lambda: factory_calls.append(1),
    )
    result = await publisher._publish_live(PublishContent(title="  ", body="\n  \n"), _target())
    assert result.ok is False
    assert "空" in result.error
    assert factory_calls == []  # 空ならブラウザを起動しない


async def test_assisted_opens_editor_and_hands_off(tmp_path, monkeypatch):
    monkeypatch.setattr(handoff_mod, "_HANDOFF_KEEPALIVE", [])
    page = _FakePage()
    launcher = _FakeLauncher(page)
    publisher = WordPressPublisher(
        session_store=_connected_store(tmp_path), launcher_factory=lambda: launcher
    )

    result = await publisher._publish_live(_content(), _target())

    assert result.ok is True and result.handed_off is True
    assert page.goto_urls == [f"https://example.com{WP_ADMIN_NEW_POST_PATH}"]
    assert page.filled[WP_TITLE_SELECTOR] == "記事タイトル"
    # assisted の契約: 最終公開は人間 — ブラウザは閉じずに開いたまま引き渡す。
    assert launcher.closed is False
    assert handoff_mod._HANDOFF_KEEPALIVE == [launcher]
