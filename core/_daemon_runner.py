"""
RepoCorp AI - Daemon Runner

`repocorp daemon start` によってサブプロセスとして起動される。
AutonomousScheduler を実行し、定期的に全 Org の改善サイクルを回す。
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
    parser = argparse.ArgumentParser(description="RepoCorp AI Autonomous Daemon")
    parser.add_argument("--interval", type=int, default=3600)
    parser.add_argument("--max-files", type=int, default=10)
    args = parser.parse_args()

    from core.scheduler import AutonomousScheduler

    scheduler = AutonomousScheduler(
        interval_seconds=args.interval,
        max_files_per_org=args.max_files,
    )
    asyncio.run(scheduler.start())


if __name__ == "__main__":
    main()
