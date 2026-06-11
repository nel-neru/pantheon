"""Pantheon - Trend Daemon Runner

`pantheon daemons start trend` / registry / frozen `--trend-daemon-run` から
サブプロセスとして起動される。TrendScheduler を実行し、定期的にトレンドを
収集→採点→人間承認ゲート付きの ContentJob/提案へ変換する。
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
    parser = argparse.ArgumentParser(description="Pantheon Trend Daemon")
    parser.add_argument("--interval", type=int, default=6 * 3600)
    parser.add_argument("--min-score", type=float, default=7.0)
    args = parser.parse_args()

    from core.trends.trend_scheduler import TrendScheduler

    scheduler = TrendScheduler(interval_seconds=args.interval, min_score=args.min_score)
    asyncio.run(scheduler.start())


if __name__ == "__main__":
    main()
