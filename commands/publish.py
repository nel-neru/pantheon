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


async def cmd_publish_auto(args: argparse.Namespace) -> None:
    """無人実送信フラグ（PUB-AUTO）の表示・切り替え。

    既定 OFF では auto ジョブも「下書き準備→人手が最終送信（handed_off）」に降格する安全運用。
    ON にしても実 auto 送信対応アダプタが揃うまでは実送信されない（Phase 2 の明示的残作業）。
    """
    from core.publishing.auto_gate import auto_send_enabled, set_auto_send_enabled

    action = getattr(args, "action", "status")
    if action == "on":
        set_auto_send_enabled(True)
        print(
            "[publish] 無人実送信フラグを ON にしました（※実 auto 送信対応アダプタが揃うまで送信はされません）"
        )
    elif action == "off":
        set_auto_send_enabled(False)
        print(
            "[publish] 無人実送信フラグを OFF にしました（auto ジョブは下書き準備→人手送信に降格）"
        )
    else:
        state = "ON" if auto_send_enabled() else "OFF（既定・安全）"
        print(f"[publish] 無人実送信フラグ: {state}")
        print("  OFF: auto ジョブは送信の直前まで自動準備し、最終送信は人手（handed_off）")
        print("  切替: pantheon publish auto on | off")


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

    sp = sub.add_parser("auto", help="無人実送信フラグの表示・切替（既定 OFF＝最終送信は人手）")
    sp.add_argument(
        "action",
        nargs="?",
        choices=["status", "on", "off"],
        default="status",
        help="状態/有効化/無効化",
    )
    sp.set_defaults(handler_name="cmd_publish_auto")
