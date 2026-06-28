"""Pantheon - Vault Sync Daemon Runner

`pantheon daemons start vault_sync` / registry / frozen `--vault-sync-daemon-run`
からサブプロセスとして起動される。VaultSyncScheduler を実行し、Obsidian 互換
Vault とストアを定期的に双方向同期する（store↔vault・LLM 非依存・ローカル I/O のみ）。
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
    parser = argparse.ArgumentParser(description="Pantheon Vault Sync Daemon")
    parser.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()

    from core.vault.sync_scheduler import VaultSyncScheduler

    scheduler = VaultSyncScheduler(interval_seconds=args.interval)
    asyncio.run(scheduler.start())


if __name__ == "__main__":
    main()
