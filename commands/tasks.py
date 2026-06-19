"""`pantheon tasks` - 作業ボード（タスクキュー）の headless 操作。

Web GUI（BoardPage / ``POST /api/tasks``）と同じグローバルタスクキュー
（``~/.pantheon/task_queue.json``）を CLI から操作する。web の drain ループは
``/ws/updates`` に GUI が接続している間だけ動くため、GUI を開かない headless /
cron 運用ではキューに積んだタスクが実行されない。``pantheon tasks drain`` は
その実行経路を明示的に開通する（GUI と同じ ``work_launcher.dispatch_task`` 経由で
wmux の work セッションへ着火する）。

  * ``add``   — タスクをキューに積む（``POST /api/tasks`` 相当）
  * ``list``  — タスク一覧を表示
  * ``drain`` — 保留タスクを並列で着火する（一発実行）
"""

from __future__ import annotations

import argparse
from typing import Any

# argparse choices 用（core を import せず CLI 起動を軽く保つ）。
# core/orchestration/task_queue.py の TaskType と同期させること。
TASK_TYPES = ("analyze", "goal", "improve", "review", "custom")


async def cmd_tasks_add(args: argparse.Namespace) -> None:
    """タスクをキューに積む（POST /api/tasks 相当）。"""
    from core.orchestration.task_queue import TaskQueue

    # analyze/review/improve は org 単位で launch_analyze にルートされる（dispatch_task）。
    # org が無いと goal に無言フォールバックして「--type analyze なのに分析されない」事故に
    # なるため、これらの型は --org を必須にする（drain の振り分けと整合させる）。
    if args.type in ("analyze", "review", "improve") and not args.org:
        print(f"[エラー] --type {args.type} は --org が必須です（org 単位で実行されます）。")
        return

    queue = TaskQueue()
    task = queue.add_task(
        args.type,
        args.org or "",
        args.description,
        priority=args.priority,
    )
    print(f"[積みました] {task['id']}  type={task['type']} priority={task['priority']}")
    print("実行: pantheon tasks drain（GUI を開いている場合は自動 drain）")


async def cmd_tasks_list(args: argparse.Namespace) -> None:
    """タスク一覧を表示する。"""
    from core.orchestration.task_queue import TaskQueue

    queue = TaskQueue()
    tasks = queue.list_tasks(org_name=args.org, status=args.status, limit=None)
    if not tasks:
        print("タスクはありません。")
        return
    for t in tasks:
        org = t.get("org_name") or "-"
        desc = (t.get("description") or "").replace("\n", " ")
        print(f"{t['id'][:8]}  {t['status']:<9} {t['type']:<8} {org:<16} {desc}")
    print(f"\n計 {len(tasks)} 件")


async def cmd_tasks_drain(args: argparse.Namespace) -> None:
    """保留タスクを並列で着火する（GUI を開かなくても headless で実行できる）。

    注意: process_pending は dispatcher が返った時点（= wmux セッションを *起動* した
    時点）でタスクを DONE にする。作業の *完了* ではなく *着火* を意味するので、出力は
    「着火」と表現する（実作業の進捗は起動したセッション側で追う）。

    drain の本体（executor を組んで pending を捌く）は web GUI / headless daemon と
    共通の :func:`core.runtime.task_drain.drain_pending_tasks` に集約している。
    """
    from core.runtime.task_drain import drain_pending_tasks

    results = await drain_pending_tasks(org_filter=args.org, max_tasks=args.max_tasks)
    if not results:
        print("着火対象の保留タスクはありません。")
        return
    fired = 0
    for r in results:
        if isinstance(r, dict) and r.get("session_id"):
            print(f"[着火] session={r['session_id']} driver={r.get('driver') or '-'}")
            fired += 1
        elif isinstance(r, dict) and r.get("error"):
            print(f"[失敗] {r['error']}")
    print(f"\n着火 {fired} 件 / 処理 {len(results)} 件")


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "tasks",
        help="作業ボード（タスクキュー）の headless 操作（add / list / drain）",
    )
    sub = parser.add_subparsers(dest="tasks_command", required=True)

    sp = sub.add_parser("add", help="タスクをキューに積む（POST /api/tasks 相当）")
    sp.add_argument("description", help="タスクの説明（goal/custom の本文にもなる）")
    sp.add_argument("--type", choices=TASK_TYPES, default="custom", help="タスク種別")
    sp.add_argument("--org", default=None, help="対象 Organization 名")
    sp.add_argument("--priority", type=int, default=5, help="優先度（大きいほど先に drain）")
    sp.set_defaults(handler_name="cmd_tasks_add")

    sp = sub.add_parser("list", help="タスク一覧を表示")
    sp.add_argument("--org", default=None, help="Organization 名で絞り込む")
    sp.add_argument("--status", default=None, help="状態で絞り込む（pending/running/done/...）")
    sp.set_defaults(handler_name="cmd_tasks_list")

    sp = sub.add_parser("drain", help="保留タスクを並列で着火（headless 実行経路）")
    sp.add_argument("--org", default=None, help="この Organization のタスクだけ着火する")
    sp.add_argument("--max-tasks", type=int, default=10, help="一度に着火する最大タスク数")
    sp.set_defaults(handler_name="cmd_tasks_drain")
