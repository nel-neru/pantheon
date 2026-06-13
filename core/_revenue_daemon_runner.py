"""Pantheon - Revenue Daemon Runner

`pantheon daemons start revenue` / daemon_registry / frozen `--revenue-daemon-run`
からサブプロセスとして起動される。RevenueScheduler を実行し、定期的に収益を分析し、
月収益目標が設定されていれば（``--target``）ポートフォリオ提案を承認ゲート付きで起票する。
LLM 非依存（``claude`` を呼ばない）ため rate-limit/quota ゲートは介さない。
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
    parser = argparse.ArgumentParser(description="Pantheon Revenue Daemon")
    parser.add_argument("--interval", type=int, default=24 * 3600)
    parser.add_argument(
        "--target",
        type=float,
        default=0.0,
        help="月収益目標（>0 でポートフォリオ提案を起票。0 以下は分析ログのみ＝アイドル）",
    )
    parser.add_argument("--source-org-name", default="HQ", dest="source_org_name")
    parser.add_argument("--min-reach", type=float, default=0.0, dest="min_reach")
    args = parser.parse_args()

    from core.hierarchy.revenue_scheduler import RevenueScheduler

    scheduler = RevenueScheduler(
        interval_seconds=args.interval,
        target=args.target,
        source_org_name=args.source_org_name,
        min_reach=args.min_reach,
    )
    asyncio.run(scheduler.start())


if __name__ == "__main__":
    main()
