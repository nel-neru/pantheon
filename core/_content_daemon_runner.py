"""Pantheon - Content Daemon Runner

`pantheon content-daemon start` / Web の `/api/content-daemon/start` でサブプロセスとして起動される。
ContentScheduler を実行し、定期的に「投稿（content_asset 提案）」を生成する PDCA ループを回す。
Claude のレート制限を検知すると自律的に停止する。
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
    parser = argparse.ArgumentParser(description="Pantheon Content/PDCA Daemon")
    parser.add_argument("--interval", type=int, default=600)
    parser.add_argument("--no-pdca", action="store_true", help="成果由来の構造介入提案を行わない")
    args = parser.parse_args()

    from core.content.content_scheduler import ContentScheduler

    scheduler = ContentScheduler(
        interval_seconds=args.interval,
        run_pdca=not args.no_pdca,
    )
    asyncio.run(scheduler.start())


if __name__ == "__main__":
    main()
