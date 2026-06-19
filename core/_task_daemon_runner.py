"""Pantheon - Task Drain Daemon Runner

`pantheon daemons start task` / registry / frozen `--task-daemon-run` から
サブプロセスとして起動される。TaskDrainScheduler を実行し、一定間隔で作業ボードの
PENDING タスクを wmux work セッション（headless 時はサブプロセス）へ着火する
=GUI を開かなくても headless で作業ボードが自動実行される。Claude のレート制限を
検知すると自律的に停止し、reset まで待って再開する。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pantheon Task Drain Daemon")
    parser.add_argument("--interval", type=int, default=120)
    parser.add_argument("--max-tasks", type=int, default=10, help="1 サイクルで着火する最大数")
    parser.add_argument("--org", default=None, help="この Organization のタスクだけ着火する")
    args = parser.parse_args()

    from core.runtime.task_drain_scheduler import TaskDrainScheduler

    scheduler = TaskDrainScheduler(
        interval_seconds=args.interval,
        max_tasks=args.max_tasks,
        org_filter=args.org,
    )
    asyncio.run(scheduler.start())


if __name__ == "__main__":
    main()
