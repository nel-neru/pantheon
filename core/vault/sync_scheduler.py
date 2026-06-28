"""VaultSyncScheduler — periodic Obsidian-vault auto-sync daemon (Phase 4).

Runs under the daemon registry as the ``vault_sync`` daemon. Each cycle it does
one bidirectional Vault sync (``import`` Obsidian edits back into the stores,
then ``export`` store state out to the vault), so the on-disk Obsidian-compatible
vault and Pantheon's knowledge stores stay in step **without** the user running
``pantheon vault sync`` by hand — this is what turns the Vault from a manual
export into a live, auto-synced knowledge base.

Unlike the trend/content daemons this does **no** model/subprocess work: vault
sync is pure local file I/O (idempotent, diff-only, non-destructive — divergent
edits land in ``<slug>.conflict.md`` rather than overwriting), so there is no
quota or rate-limit gating here. It only emits heartbeats like the other daemons.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.runtime.heartbeat import write_heartbeat

logger = logging.getLogger(__name__)

HEARTBEAT_NAME = "vault_sync"
DEFAULT_VAULT_SYNC_INTERVAL_SECONDS = 300  # 5 分ごと（同期は冪等＆安価なので短め）
SLEEP_CHUNK_SECONDS = 60.0

STATUS_RUNNING = "running"
STATUS_STOPPED = "stopped"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VaultSyncScheduler:
    """Obsidian 互換 Vault を定期的に双方向同期する daemon（LLM 非依存・ローカル I/O のみ）。"""

    def __init__(
        self,
        platform_home: Optional[Path] = None,
        interval_seconds: int = DEFAULT_VAULT_SYNC_INTERVAL_SECONDS,
        **_kwargs: Any,
    ):
        from core.platform.state import PlatformStateManager

        self._psm = PlatformStateManager(platform_home)
        self.platform_home = self._psm.platform_home
        self._interval = max(60, interval_seconds)
        self._running = False
        self._cycle_count = 0
        self._status = STATUS_STOPPED
        self._log_path = self.platform_home / "vault_sync_log.jsonl"

    async def start(self) -> None:
        self._running = True
        logger.info("VaultSyncScheduler started (interval=%ds)", self._interval)
        try:
            while self._running:
                self._beat(STATUS_RUNNING)
                await self.run_cycle()
                # interval をチャンク分割して stop() に即応する（trend/content と同パターン）。
                waited = 0.0
                while self._running and waited < self._interval:
                    self._beat(STATUS_RUNNING)
                    chunk = min(SLEEP_CHUNK_SECONDS, self._interval - waited)
                    await asyncio.sleep(chunk)
                    waited += chunk
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            self._beat(STATUS_STOPPED)

    def stop(self) -> None:
        self._running = False

    async def run_cycle(self) -> Dict[str, Any]:
        """1 サイクル: Vault を 1 往復同期（import→export）。

        失敗は黙殺せず ``error`` として log に残す（daemon は次サイクルで再試行）。
        """
        self._cycle_count += 1
        started = _now_iso()
        summary: Dict[str, Any] = {"cycle": self._cycle_count, "started_at": started}
        try:
            from core.vault import build_default_sync

            result = build_default_sync(self.platform_home).sync()
            imported = result.get("import", {})
            exported = result.get("export", {})
            summary.update(
                {
                    "completed_at": _now_iso(),
                    "imported": imported.get("imported", 0),
                    "exported": exported.get("written", 0),
                    "conflicts": result.get("conflicts", 0),
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("vault sync failed: %s", exc)
            summary.update({"completed_at": _now_iso(), "error": str(exc)})
        self._write_log(summary)
        return summary

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "status": self._status,
            "cycle_count": self._cycle_count,
            "interval_seconds": self._interval,
        }

    def _beat(self, status: str) -> None:
        self._status = status
        write_heartbeat(
            HEARTBEAT_NAME,
            {"status": status, "cycle": self._cycle_count, "interval_seconds": self._interval},
            platform_home=self.platform_home,
        )

    def _write_log(self, data: Dict[str, Any]) -> None:
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def get_recent_logs(self, n: int = 20) -> List[Dict[str, Any]]:
        if not self._log_path.exists():
            return []
        lines = self._log_path.read_text(encoding="utf-8").strip().splitlines()
        out: List[Dict[str, Any]] = []
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out
