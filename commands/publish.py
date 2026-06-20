"""`pantheon publish` - 投稿基盤のブラウザセッション接続管理＋投稿ジョブの実行（Track E）。

資格情報は保存しない: ``connect`` はヘッドフルブラウザを開き、ユーザー自身が
ログインしたら Playwright の storage_state（cookie 等）だけを
``~/.pantheon/browser_sessions/<platform>/`` に保存する。

``publish jobs run/confirm`` は GUI（``/api/publish-jobs/{id}/run|confirm``）と同じ
``core.publishing.runner`` を呼ぶ。**承認ゲートと auto_gate はそのまま維持**される
（auto OFF の既定では実送信されず handed_off＝人手の最終公開待ちへ降格する）ため、
headless/自律パスからも安全に「下書き→人手公開→確認」を進められる（パリティのため CLI を開く）。
"""

from __future__ import annotations

import argparse
import sys
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


def _publish_job_store():
    from core.publishing.publish_jobs import PublishJobStore

    return PublishJobStore()


async def cmd_publish_jobs_list(args: argparse.Namespace) -> None:
    """投稿ジョブ一覧（任意で --status / --org 絞り込み）。"""
    jobs = _publish_job_store().list_jobs()
    status = getattr(args, "status", None)
    org_name = getattr(args, "org_name", None)
    if status:
        jobs = [j for j in jobs if j.status == status]
    if org_name:
        jobs = [j for j in jobs if j.org_name == org_name]
    if not jobs:
        print("投稿ジョブはありません。")
        return
    print(f"\n投稿ジョブ一覧（{len(jobs)} 件）\n")
    for j in jobs:
        print(
            f"  {j.job_id[:8]}  [{j.status:<10}] {j.platform:<10} {j.org_name}"
            f"  {j.title or '(無題)'}"
        )
    print("\n実行: pantheon publish jobs run <id> / 公開確認: pantheon publish jobs confirm <id>")


async def cmd_publish_jobs_run(args: argparse.Namespace) -> None:
    """投稿ジョブを実行する（--dry-run でプレビューのみ・auto_gate と承認ゲートは維持）。"""
    from core.platform.state import get_platform_home
    from core.publishing.runner import run_publish_job

    store = _publish_job_store()
    job = store.get_job(args.job_id)
    if job is None:
        print(f"[ERROR] 投稿ジョブ '{args.job_id}' が見つかりません")
        sys.exit(1)
    if job.status == "handed_off" and not args.dry_run:
        # GUI と同じ防御: handed_off は再実行不可（出口は confirm のみ）。
        print(
            "[ERROR] 人手の最終公開待ち（handed_off）のジョブは再実行できません。"
            "公開済みなら pantheon publish jobs confirm <id> で確定してください"
        )
        sys.exit(1)
    result = await run_publish_job(
        job, store=store, platform_home=get_platform_home(), dry_run=args.dry_run
    )
    if result.get("ok"):
        if result.get("handed_off"):
            print("[OK] 下書きを引き渡しました（人手で公開→ confirm で確定してください）")
        else:
            print(f"[OK] {result.get('detail') or result.get('url') or '実行しました'}")
    else:
        print(f"[NG] {result.get('error') or result.get('detail') or '失敗しました'}")
        sys.exit(1)


async def cmd_publish_jobs_confirm(args: argparse.Namespace) -> None:
    """handed_off（人手の公開待ち）のジョブを公開済みとして確定し成果を記録する。"""
    from core.platform.state import get_platform_home
    from core.publishing.runner import confirm_handed_off

    store = _publish_job_store()
    if store.get_job(args.job_id) is None:
        print(f"[ERROR] 投稿ジョブ '{args.job_id}' が見つかりません")
        sys.exit(1)
    result = confirm_handed_off(
        args.job_id, store=store, platform_home=get_platform_home(), result_url=args.url or ""
    )
    if not result.get("ok"):
        print(f"[ERROR] {result.get('error') or '確認できません'}")
        sys.exit(1)
    print(f"[OK] 公開を確認しました{('：' + result['url']) if result.get('url') else ''}")


async def cmd_publish_jobs_delete(args: argparse.Namespace) -> None:
    """投稿ジョブを削除する。"""
    if not _publish_job_store().delete_job(args.job_id):
        print(f"[ERROR] 投稿ジョブ '{args.job_id}' が見つかりません")
        sys.exit(1)
    print(f"[OK] 削除しました: {args.job_id}")


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

    jobs_p = sub.add_parser(
        "jobs", help="投稿ジョブの一覧/実行/公開確認/削除（承認ゲート・auto_gate は維持）"
    )
    jobs_sub = jobs_p.add_subparsers(dest="publish_jobs_command", required=True)

    jl = jobs_sub.add_parser("list", help="投稿ジョブ一覧（--status / --org で絞り込み）")
    jl.add_argument(
        "--status", default=None, help="status で絞り込み（queued/handed_off/published…）"
    )
    jl.add_argument("--org", default=None, dest="org_name", help="org_name で絞り込み")
    jl.set_defaults(handler_name="cmd_publish_jobs_list")

    jr = jobs_sub.add_parser("run", help="投稿ジョブを実行（--dry-run でプレビュー）")
    jr.add_argument("job_id", help="投稿ジョブ id")
    jr.add_argument("--dry-run", action="store_true", dest="dry_run", help="送信せずプレビューのみ")
    jr.set_defaults(handler_name="cmd_publish_jobs_run")

    jc = jobs_sub.add_parser("confirm", help="handed_off のジョブを公開済みとして確定")
    jc.add_argument("job_id", help="投稿ジョブ id")
    jc.add_argument("--url", default="", help="実際に公開した URL（任意・成果に紐づけ）")
    jc.set_defaults(handler_name="cmd_publish_jobs_confirm")

    jd = jobs_sub.add_parser("delete", help="投稿ジョブを削除")
    jd.add_argument("job_id", help="投稿ジョブ id")
    jd.set_defaults(handler_name="cmd_publish_jobs_delete")
