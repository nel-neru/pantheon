"""手動ログインによるブラウザセッション接続フロー（Track E のコア）。

ヘッドフルブラウザを開いてユーザー自身にログインしてもらい、ログイン成功を
セッション cookie の出現で検知したら Playwright の storage_state だけを
``~/.pantheon/browser_sessions/<platform>/state.json`` へ保存する。
パスワード等の資格情報を Pantheon が受け取る・保存することは一切ない
（``session.py`` と同じ方針）。

Playwright は遅延 import（``playwright_available()`` ゲート）。テストは
``launcher=`` にフェイクを注入してフロー論理だけを検証する（実ブラウザ不要）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

from core.publishing.base import PLATFORM_NOTE, PLATFORM_X, playwright_available
from core.publishing.session import SessionStore

# 手動ログインを開始する URL。wordpress はサイト URL 依存のため接続フロー対象外
# （Phase 2 で REST API 接続を検討する）。
LOGIN_URLS: Dict[str, str] = {
    PLATFORM_NOTE: "https://note.com/login",
    PLATFORM_X: "https://x.com/i/flow/login",
}

# 「ログイン済み」を示すセッション cookie 名（プレフィックス一致）。
# note は版付き（例: _note_session_v5）のためプレフィックスで版上げに耐える。
_SESSION_COOKIE_HINTS: Dict[str, Tuple[str, ...]] = {
    PLATFORM_NOTE: ("_note_session",),
    PLATFORM_X: ("auth_token",),
}

# cookie 名だけの一致では他ドメインの同名 cookie を誤検知しうるため、
# 発行ドメインも照合する（x は twitter.com 時代の cookie も受け入れる）。
_SESSION_COOKIE_DOMAINS: Dict[str, Tuple[str, ...]] = {
    PLATFORM_NOTE: ("note.com",),
    PLATFORM_X: ("x.com", "twitter.com"),
}

DEFAULT_TIMEOUT_S = 300.0
DEFAULT_POLL_INTERVAL_S = 2.0


@dataclass
class ConnectResult:
    """接続フローの結果。``ok=False`` のときは ``error`` に理由を入れる。"""

    ok: bool
    platform: str
    error: str = ""
    detail: str = ""
    state_path: str = ""


class PlaywrightLauncher:
    """実 Playwright でヘッドフルブラウザを開く既定のランチャ。

    契約は ``launch() -> context`` / ``close()`` の 2 メソッドのみ。テストは
    同じ契約のフェイクを ``interactive_login(launcher=...)`` に注入する。
    ``storage_state`` を渡すと保存済みセッションを復元した context を開く
    （アダプタの実投稿/ハンドオフでも再利用する）。
    """

    def __init__(self, storage_state: Optional[str] = None) -> None:
        self._pw: Any = None
        self._browser: Any = None
        self._storage_state = storage_state

    async def launch(self) -> Any:
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=False)
        if self._storage_state is not None:
            return await self._browser.new_context(storage_state=self._storage_state)
        return await self._browser.new_context()

    def is_alive(self) -> bool:
        """ブラウザがまだ開いているか（ハンドオフ残骸の後始末判定に使う）。"""
        try:
            return bool(self._browser is not None and self._browser.is_connected())
        except Exception:  # noqa: BLE001
            return False

    async def close(self) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
        finally:
            if self._pw is not None:
                await self._pw.stop()


def _hint_matched(cookies: Iterable[dict], platform: str) -> bool:
    hints = _SESSION_COOKIE_HINTS.get(platform, ())
    domains = _SESSION_COOKIE_DOMAINS.get(platform, ())
    for cookie in cookies:
        name = str(cookie.get("name", ""))
        domain = str(cookie.get("domain", "")).lstrip(".")
        if any(name.startswith(h) for h in hints) and any(
            domain == d or domain.endswith("." + d) for d in domains
        ):
            return True
    return False


async def interactive_login(
    platform: str,
    *,
    session_store: Optional[SessionStore] = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    launcher: Any = None,
) -> ConnectResult:
    """ヘッドフルブラウザで手動ログインしてもらい、storage_state を保存する。

    例外を投げず ``ConnectResult`` で正直に成否を返す（CLI / API 双方から使うため）。
    ログイン検知前にブラウザが閉じられた場合、state は保存できないので未接続のまま。
    """
    if platform not in LOGIN_URLS:
        return ConnectResult(
            ok=False, platform=platform, error=f"接続フロー未対応のプラットフォーム: {platform}"
        )
    if launcher is None:
        if not playwright_available():
            return ConnectResult(
                ok=False,
                platform=platform,
                error=(
                    "Playwright 未導入（または PANTHEON_NO_BROWSER=1）のため接続フローを"
                    "起動できません。`pip install playwright && playwright install chromium`"
                    " で導入できます"
                ),
            )
        launcher = PlaywrightLauncher()

    store = session_store or SessionStore()
    store.ensure_dir(platform)
    state_path = store.state_path(platform)

    try:
        try:
            context = await launcher.launch()
            page = await context.new_page()
            await page.goto(LOGIN_URLS[platform])
        except Exception as exc:  # noqa: BLE001 — 起動失敗は理由つきで正直に返す
            return ConnectResult(
                ok=False,
                platform=platform,
                error=(
                    f"ブラウザ起動に失敗しました: {type(exc).__name__}: {exc}"
                    "（初回は `playwright install chromium` が必要な場合があります）"
                ),
            )

        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.0, timeout_s)
        while True:
            try:
                cookies = await context.cookies()
            except Exception:  # noqa: BLE001 — ユーザーがブラウザごと閉じた等
                return ConnectResult(
                    ok=False,
                    platform=platform,
                    error=(
                        "ログイン検知前にブラウザが閉じられました。もう一度実行し、"
                        "接続完了が表示されるまでウィンドウを開いたままにしてください"
                    ),
                )
            if _hint_matched(cookies, platform):
                try:
                    await context.storage_state(path=str(state_path))
                except Exception as exc:  # noqa: BLE001
                    return ConnectResult(
                        ok=False,
                        platform=platform,
                        error=f"セッション state の保存に失敗しました: {type(exc).__name__}: {exc}",
                    )
                # state.json は実質ベアラ秘密（ログイン済み cookie）なので、GUI settings
                # ファイルと同じ基準で所有者限定パーミッションにする（Windows は best-effort）。
                try:
                    state_path.chmod(0o600)
                except OSError:
                    pass
                return ConnectResult(
                    ok=True,
                    platform=platform,
                    detail="ログインを検知し、セッション state を保存しました（資格情報は保存していません）",
                    state_path=str(state_path),
                )
            if loop.time() >= deadline:
                return ConnectResult(
                    ok=False,
                    platform=platform,
                    error=f"タイムアウト（{int(timeout_s)}秒）: ログインを検知できませんでした",
                )
            await asyncio.sleep(poll_interval_s)
    finally:
        try:
            await launcher.close()
        except Exception:  # noqa: BLE001 — close 失敗で本来の結果を上書きしない
            pass
