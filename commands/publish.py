"""`pantheon publish` - 投稿基盤のブラウザセッション接続管理（Track E）。

資格情報は保存しない: ``connect`` はヘッドフルブラウザを開き、ユーザー自身が
ログインしたら Playwright の storage_state（cookie 等）だけを
``~/.pantheon/browser_sessions/<platform>/`` に保存する。投稿ジョブ自体の
作成・実行は承認ゲート（content_asset 提案の承認）経由のみで、この CLI からは行わない。
"""

from __future__ import annotations

import argparse
from typing import Any

# argparse の choices 用（core を import せず CLI 起動を軽く保つ）。
# core/publishing/connect.py の LOGIN_URLS / base.py の SUPPORTED_PLATFORMS と同期させること。
CONNECTABLE_PLATFORMS = ("note", "x")
ALL_PLATFORMS = ("note", "x", "wordpress")


async def cmd_publish_connect(args: argparse.Namespace) -> None:
    """ヘッドフルブラウザで手動ログインし、セッション state を保存する。"""
    from core.publishing.connect import interactive_login

    print(
        f"[{args.platform}] ヘッドフルブラウザを起動します。開いたウィンドウでログインしてください…"
    )
    result = await interactive_login(args.platform, timeout_s=float(args.timeout))
    if result.ok:
        print(f"[OK]    {result.detail}")
        print(f"        state: {result.state_path}")
    else:
        print(f"[ERROR] {result.error}")


async def cmd_publish_status(args: argparse.Namespace) -> None:
    """各プラットフォームの接続状態を表示する。"""
    from core.publishing.session import SessionStore

    for st in SessionStore().list_connections():
        mark = "[OK]  " if st.status == "connected" else "[NONE]"
        suffix = f" connected_at={st.connected_at}" if st.connected_at else ""
        print(f"{mark} {st.platform:<10} {st.status}{suffix}")


async def cmd_publish_disconnect(args: argparse.Namespace) -> None:
    """保存済みセッション state を削除して切断する。"""
    from core.publishing.session import SessionStore

    cleared = SessionStore().clear(args.platform)
    if cleared:
        print(f"[{args.platform}] 切断しました（セッション state を削除）")
    else:
        print(f"[{args.platform}] 保存済みセッションはありません")


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "publish",
        help="投稿基盤のブラウザセッション接続管理（connect / status / disconnect）",
    )
    sub = parser.add_subparsers(dest="publish_command", required=True)

    sp = sub.add_parser(
        "connect", help="ヘッドフルブラウザで手動ログインし、セッション state を保存"
    )
    sp.add_argument("platform", choices=CONNECTABLE_PLATFORMS)
    sp.add_argument("--timeout", type=int, default=300, help="ログイン検知の待ち時間（秒）")
    sp.set_defaults(handler_name="cmd_publish_connect")

    sp = sub.add_parser("status", help="各プラットフォームの接続状態を表示")
    sp.set_defaults(handler_name="cmd_publish_status")

    sp = sub.add_parser("disconnect", help="保存済みセッション state を削除して切断")
    sp.add_argument("platform", choices=ALL_PLATFORMS)
    sp.set_defaults(handler_name="cmd_publish_disconnect")
