"""接続フロー（interactive_login）のテスト — 実ブラウザは起動しない。

フェイクの launcher/context を注入してフロー論理（ログイン検知→state 保存、
タイムアウト、ブラウザ閉鎖、起動失敗の正直な報告）だけを検証する。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.publishing.connect import LOGIN_URLS, interactive_login
from core.publishing.session import SessionStore


class _FakePage:
    def __init__(self) -> None:
        self.goto_urls: list[str] = []

    async def goto(self, url: str) -> None:
        self.goto_urls.append(url)


class _FakeContext:
    """``cookies()`` が呼ばれるたびに batches を順に返す（最後の要素は維持）。"""

    def __init__(self, batches=None, *, cookies_error=None, state_error=None):
        self._batches = list(batches or [])
        self._cookies_error = cookies_error
        self._state_error = state_error
        self.page: _FakePage | None = None
        self.saved_paths: list[str] = []

    async def new_page(self) -> _FakePage:
        self.page = _FakePage()
        return self.page

    async def cookies(self):
        if self._cookies_error is not None:
            raise self._cookies_error
        if not self._batches:
            return []
        if len(self._batches) > 1:
            return self._batches.pop(0)
        return self._batches[0]

    async def storage_state(self, path: str):
        if self._state_error is not None:
            raise self._state_error
        Path(path).write_text(json.dumps({"cookies": [{"name": "stub"}]}), encoding="utf-8")
        self.saved_paths.append(str(path))
        return {}


class _FakeLauncher:
    def __init__(self, context=None, *, launch_error=None):
        self._context = context
        self._launch_error = launch_error
        self.closed = False

    async def launch(self):
        if self._launch_error is not None:
            raise self._launch_error
        return self._context

    async def close(self) -> None:
        self.closed = True


async def test_unsupported_platform_fails_honestly(tmp_path):
    result = await interactive_login(
        "wordpress", session_store=SessionStore(platform_home=tmp_path)
    )
    assert result.ok is False
    assert "未対応" in result.error


async def test_no_playwright_fails_honestly(tmp_path, monkeypatch):
    monkeypatch.setenv("PANTHEON_NO_BROWSER", "1")
    result = await interactive_login("note", session_store=SessionStore(platform_home=tmp_path))
    assert result.ok is False
    assert "Playwright" in result.error


async def test_login_detected_saves_state(tmp_path):
    store = SessionStore(platform_home=tmp_path)
    ctx = _FakeContext([[], [{"name": "_note_session_v5", "value": "s", "domain": ".note.com"}]])
    launcher = _FakeLauncher(ctx)

    result = await interactive_login(
        "note", session_store=store, launcher=launcher, timeout_s=30, poll_interval_s=0
    )

    assert result.ok is True
    assert store.is_connected("note") is True
    assert result.state_path == str(store.state_path("note"))
    assert ctx.page is not None and ctx.page.goto_urls == [LOGIN_URLS["note"]]
    assert launcher.closed is True  # 成功してもブラウザは必ず後始末される


async def test_x_login_detected_by_auth_token(tmp_path):
    store = SessionStore(platform_home=tmp_path)
    ctx = _FakeContext([[{"name": "auth_token", "value": "t", "domain": ".x.com"}]])

    result = await interactive_login(
        "x", session_store=store, launcher=_FakeLauncher(ctx), poll_interval_s=0
    )

    assert result.ok is True
    assert store.is_connected("x") is True


async def test_session_cookie_name_on_wrong_domain_does_not_count(tmp_path):
    """名前が一致しても発行ドメインが違う cookie はログイン扱いしない（誤検知防止）。"""
    store = SessionStore(platform_home=tmp_path)
    ctx = _FakeContext([[{"name": "_note_session_v5", "value": "s", "domain": ".evil.example"}]])

    result = await interactive_login(
        "note", session_store=store, launcher=_FakeLauncher(ctx), timeout_s=0, poll_interval_s=0
    )

    assert result.ok is False
    assert store.is_connected("note") is False


async def test_unrelated_cookies_time_out_without_saving(tmp_path):
    store = SessionStore(platform_home=tmp_path)
    ctx = _FakeContext([[{"name": "_ga", "value": "analytics"}]])
    launcher = _FakeLauncher(ctx)

    result = await interactive_login(
        "note", session_store=store, launcher=launcher, timeout_s=0, poll_interval_s=0
    )

    assert result.ok is False
    assert "タイムアウト" in result.error
    assert store.is_connected("note") is False  # 未ログインの state は保存しない
    assert launcher.closed is True


async def test_browser_closed_before_login_is_honest(tmp_path):
    store = SessionStore(platform_home=tmp_path)
    ctx = _FakeContext(cookies_error=RuntimeError("browser has been closed"))
    launcher = _FakeLauncher(ctx)

    result = await interactive_login(
        "note", session_store=store, launcher=launcher, poll_interval_s=0
    )

    assert result.ok is False
    assert "閉じられました" in result.error
    assert store.is_connected("note") is False
    assert launcher.closed is True


async def test_launch_failure_reports_install_hint(tmp_path):
    store = SessionStore(platform_home=tmp_path)
    launcher = _FakeLauncher(launch_error=RuntimeError("Executable doesn't exist"))

    result = await interactive_login(
        "note", session_store=store, launcher=launcher, poll_interval_s=0
    )

    assert result.ok is False
    assert "起動に失敗" in result.error
    assert "playwright install" in result.error
    assert launcher.closed is True


async def test_state_save_failure_is_honest(tmp_path):
    store = SessionStore(platform_home=tmp_path)
    ctx = _FakeContext(
        [[{"name": "_note_session_v5", "domain": ".note.com"}]], state_error=OSError("disk full")
    )

    result = await interactive_login(
        "note", session_store=store, launcher=_FakeLauncher(ctx), poll_interval_s=0
    )

    assert result.ok is False
    assert "保存に失敗" in result.error
    assert store.is_connected("note") is False


def test_cli_platform_choices_in_sync():
    """CLI の choices（CLI 起動を軽く保つためのハードコード）と core 定義の同期を強制する。"""
    from commands.publish import ALL_PLATFORMS, CONNECTABLE_PLATFORMS
    from core.publishing.base import SUPPORTED_PLATFORMS

    assert set(CONNECTABLE_PLATFORMS) == set(LOGIN_URLS)
    assert set(ALL_PLATFORMS) == set(SUPPORTED_PLATFORMS)


async def test_cli_publish_status_lists_all_platforms(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    from commands.publish import cmd_publish_status

    await cmd_publish_status(argparse.Namespace())

    out = capsys.readouterr().out
    for platform in ("note", "x", "wordpress"):
        assert platform in out
