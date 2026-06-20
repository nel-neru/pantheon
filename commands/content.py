"""`pantheon content` — 定期コンテンツ生成ジョブ（ContentJob）の CLI。

GUI（/content の ContentSchedulePage / `/api/content-jobs*`）と同等の機能を CLI・自律パスへ開く。
ジョブの作成/一覧/有効化/無効化/即時実行/削除を行う。実行は ``content_runner.run_content_job``
が担い、生成物は ``content_asset`` 提案として **人間承認待ち**で repo に残る（外部公開はしない）。

これまで content ジョブは Web 専用で、headless/evolve/daemon は content デーモンを「回す」ことしか
できなかった（個別ジョブの作成/確認/単発実行が不可）。この CLI がその最大のパリティギャップを埋める。
"""

from __future__ import annotations

import argparse
import sys
from typing import Any


def _store():
    from core.content.content_jobs import ContentJobStore

    return ContentJobStore()


def _print_job(job: Any) -> None:
    flag = "✓" if job.enabled else "×"
    pub = f" → {job.publish_platform}/{job.publish_mode}" if job.publish_platform else ""
    print(
        f"  [{flag}] {job.job_id[:8]}  {job.kind:<16} {job.org_name}"
        f"  「{job.theme or '(テーマ未設定)'}」{pub}"
    )
    print(
        f"        間隔 {job.interval_seconds}s / 実行 {job.run_count} 回 / 状態 {job.last_status}"
    )


async def cmd_content_list(args: argparse.Namespace) -> None:
    """コンテンツ生成ジョブを一覧表示する。"""
    jobs = _store().list_jobs()
    if not jobs:
        print("コンテンツジョブがありません。pantheon content create で作成してください。")
        return
    print(f"\nコンテンツジョブ一覧（{len(jobs)} 件）\n")
    for job in jobs:
        _print_job(job)


async def cmd_content_create(args: argparse.Namespace) -> None:
    """コンテンツ生成ジョブを作成する（対象は実在の repo 紐づき組織）。"""
    from core.bootstrap import bootstrap_platform
    from core.content.content_jobs import CONTENT_JOB_KINDS, ContentJob

    psm = bootstrap_platform()
    org = psm.load_organization_by_name(args.org)
    if org is None:
        print(f"[ERROR] Organization '{args.org}' が見つかりません")
        sys.exit(1)
    if not getattr(org, "target_repo_path", None):
        print(f"[ERROR] Organization '{args.org}' に repo（ワークスペース）が未設定です")
        sys.exit(1)
    if args.kind not in CONTENT_JOB_KINDS:
        print(f"[ERROR] kind は {'/'.join(CONTENT_JOB_KINDS)} のいずれかです")
        sys.exit(1)

    job = ContentJob(
        org_name=args.org,
        kind=args.kind,
        theme=args.theme or "",
        interval_seconds=args.interval,
        enabled=not args.disabled,
        publish_platform=args.platform or "",
        publish_mode=args.mode or "assisted",
    )
    _store().add_job(job)
    print(f"\n[OK] コンテンツジョブを作成しました: {job.job_id[:8]}")
    _print_job(job)
    print("\n即時実行: pantheon content run " + job.job_id)


async def cmd_content_run(args: argparse.Namespace) -> None:
    """ジョブを即時実行し、投稿ドラフト（content_asset 提案・承認待ち）を生成する。"""
    from core.bootstrap import bootstrap_platform
    from core.content.content_runner import run_content_job

    store = _store()
    job = store.get_job(args.job_id)
    if job is None:
        print(f"[ERROR] ジョブ '{args.job_id}' が見つかりません")
        sys.exit(1)
    result = await run_content_job(job, bootstrap_platform())
    store.mark_run(job.job_id, status=result.get("status", "done"), detail=result.get("detail", ""))
    if result.get("ok"):
        print(f"\n[OK] {result.get('detail', '生成しました')}")
        print(f"  提案 id: {result.get('proposal_id')}（/inbox または proposal apply で承認）")
    else:
        print(f"\n[NG] {result.get('status')}: {result.get('detail', '')}")
        sys.exit(1)


async def cmd_content_enable(args: argparse.Namespace) -> None:
    """ジョブを有効化する。"""
    job = _store().set_enabled(args.job_id, True)
    if job is None:
        print(f"[ERROR] ジョブ '{args.job_id}' が見つかりません")
        sys.exit(1)
    print(f"[OK] 有効化しました: {job.job_id[:8]}")


async def cmd_content_disable(args: argparse.Namespace) -> None:
    """ジョブを無効化する（次回以降スケジュールされない）。"""
    job = _store().set_enabled(args.job_id, False)
    if job is None:
        print(f"[ERROR] ジョブ '{args.job_id}' が見つかりません")
        sys.exit(1)
    print(f"[OK] 無効化しました: {job.job_id[:8]}")


async def cmd_content_delete(args: argparse.Namespace) -> None:
    """ジョブを削除する。"""
    if not _store().delete_job(args.job_id):
        print(f"[ERROR] ジョブ '{args.job_id}' が見つかりません")
        sys.exit(1)
    print(f"[OK] 削除しました: {args.job_id}")


def register(subparsers: Any) -> None:
    from core.content.content_jobs import CONTENT_JOB_KINDS

    parser = subparsers.add_parser("content", help="定期コンテンツ生成ジョブの管理（GUI と同等）")
    sub = parser.add_subparsers(dest="content_command", required=True)

    sub.add_parser("list", help="コンテンツジョブを一覧表示").set_defaults(
        handler_name="cmd_content_list"
    )

    create_p = sub.add_parser("create", help="コンテンツ生成ジョブを作成")
    create_p.add_argument("--org", required=True, help="対象 Organization 名（repo 紐づき必須）")
    create_p.add_argument(
        "--kind", default="content_brief", help=f"種別: {'/'.join(CONTENT_JOB_KINDS)}"
    )
    create_p.add_argument("--theme", default="", help="生成テーマ")
    create_p.add_argument(
        "--interval", type=int, default=86400, dest="interval", help="生成間隔（秒・既定 1 日）"
    )
    create_p.add_argument("--platform", default="", help="投稿先（note/x/wordpress・任意）")
    create_p.add_argument(
        "--mode", default="assisted", help="投稿モード（assisted/auto・既定 assisted）"
    )
    create_p.add_argument("--disabled", action="store_true", help="無効状態で作成する")
    create_p.set_defaults(handler_name="cmd_content_create")

    run_p = sub.add_parser("run", help="ジョブを即時実行して下書きを生成（承認待ち）")
    run_p.add_argument("job_id", help="ジョブ id")
    run_p.set_defaults(handler_name="cmd_content_run")

    enable_p = sub.add_parser("enable", help="ジョブを有効化")
    enable_p.add_argument("job_id", help="ジョブ id")
    enable_p.set_defaults(handler_name="cmd_content_enable")

    disable_p = sub.add_parser("disable", help="ジョブを無効化")
    disable_p.add_argument("job_id", help="ジョブ id")
    disable_p.set_defaults(handler_name="cmd_content_disable")

    del_p = sub.add_parser("delete", help="ジョブを削除")
    del_p.add_argument("job_id", help="ジョブ id")
    del_p.set_defaults(handler_name="cmd_content_delete")
