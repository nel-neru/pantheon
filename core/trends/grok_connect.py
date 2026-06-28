"""Grok への一度きり手動ログイン（接続）と接続状態の管理（薄いラッパ）。

publishing の ``interactive_login`` を Grok 用の遷移先 URL とログイン判定述語付きで呼ぶだけの層。
Grok はログイン後の cookie 名が不明なため、cookie ヒント照合ではなく「grok.com のチャット UI に
遷移＋コンポーザ入力欄の存在」で判定する（``_grok_logged_in``）。セッションは publishing と同じ
``SessionStore`` の platform="grok"（``~/.pantheon/browser_sessions/grok/state.json``）に保存する。
資格情報は一切保存しない（Playwright の storage_state ＝ cookie のみ。``connect.py`` と同方針）。
"""

from __future__ import annotations

from typing import Any, Optional

from core.publishing.connect import ConnectResult, interactive_login
from core.publishing.session import ConnectionStatus, SessionStore
from core.trends.collectors.grok import (
    COMPOSER_SELECTORS,
    GROK_PLATFORM,
    GROK_URL,
    _find_visible,
)

# ゲスト（未ログイン）導線のラベル。これらのボタン/リンクが在る間は未ログインとみなす。
_GUEST_MARKERS = ("サインイン", "新規登録", "ログイン", "Sign in", "Sign up", "Log in")


async def _grok_logged_in(context: Any, page: Any) -> bool:
    """grok.com で「実際にログイン済み」かを判定する（cookie 非依存）。

    grok.com は **ゲスト（未ログイン）でも入力欄 'Ask Grok anything' を出す**ため、入力欄の存在
    だけだと false positive になる（送信しても「会話を続ける/ご登録ください」で生成されない）。
    そこで「入力欄が在り、かつ サインイン/新規登録 等のゲスト導線が無い」ことを真のログインとみなす。
    """
    try:
        url = str(getattr(page, "url", "") or "")
    except Exception:  # noqa: BLE001
        url = ""
    if "grok.com" not in url:
        return False
    if (await _find_visible(page, COMPOSER_SELECTORS)) is None:
        return False
    try:
        has_guest_cta = await page.evaluate(
            """(markers) => {
              const els = Array.from(document.querySelectorAll('button,a'));
              return els.some(e => {
                const t = (e.innerText || '').trim();
                return !!t && markers.some(m => t === m || t.includes(m));
              });
            }""",
            list(_GUEST_MARKERS),
        )
    except Exception:  # noqa: BLE001 — 判定不能時は安全側（未ログイン扱い）で偽陽性を避ける
        return False
    return not has_guest_cta


async def connect_grok(
    *,
    session_store: Optional[SessionStore] = None,
    timeout_s: float = 300.0,
    launcher: Any = None,
) -> ConnectResult:
    """ヘッドフルブラウザで grok.com に手動ログインし、セッション state を保存する。

    例外を投げず ``ConnectResult`` で成否を返す（CLI / API 双方から使うため）。
    """
    return await interactive_login(
        GROK_PLATFORM,
        session_store=session_store,
        timeout_s=timeout_s,
        launcher=launcher,
        login_url=GROK_URL,
        is_logged_in=_grok_logged_in,
    )


def grok_status(session_store: Optional[SessionStore] = None) -> ConnectionStatus:
    """Grok の接続状態（connected/disconnected）を返す。"""
    store = session_store or SessionStore()
    return store.status(GROK_PLATFORM)


def disconnect_grok(session_store: Optional[SessionStore] = None) -> bool:
    """保存済み Grok セッション state を削除する（切断）。保存が無ければ False。"""
    store = session_store or SessionStore()
    return store.clear(GROK_PLATFORM)
