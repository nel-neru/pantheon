"""TaskDrainScheduler — 作業ボードの headless 自動実行 daemon。

daemon レジストリの ``task`` として動く（既定オフ・opt-in）。GUI の自動 drain は
``/ws/updates`` に GUI が接続している間だけ動くため、GUI を開かない 24/7 運用では
``POST /api/tasks`` / ``pantheon tasks add`` で積んだタスクが実行されない。本 daemon
は一定間隔で PENDING タスクを :func:`core.runtime.task_drain.drain_pending_tasks`
経由で wmux work セッション（headless 時はサブプロセス）へ着火し、真の headless
自動実行を開通する。

他の daemon と同じく、レート制限（共有ゲート）で pause→reset まで待ち、トークン
クォータが逼迫している間は新規タスクを着火しない（background 優先度）。着火は
*起動* であって *完了* ではない点に注意（作業の進捗は起動したセッション側で追う）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.runtime.heartbeat import write_heartbeat
from core.runtime.quota_governor import PRIORITY_BACKGROUND, QuotaGovernor
from core.runtime.rate_limit import DEFAULT_BACKOFF, MAX_BACKOFF
from core.runtime.usage_gate import RateLimitGate

logger = logging.getLogger(__name__)

HEARTBEAT_NAME = "task"
DEFAULT_TASK_DRAIN_INTERVAL_SECONDS = 120  # 2 分ごとに作業ボードを drain
PAUSE_SLEEP_CHUNK_SECONDS = 60.0

STATUS_RUNNING = "running"
STATUS_PAUSED_RATE_LIMIT = "paused_rate_limit"
STATUS_STOPPED = "stopped"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskDrainScheduler:
    """作業ボードの PENDING タスクを定期 drain する daemon（background 優先度・レート制限対応）。"""

    def __init__(
        self,
        platform_home: Optional[Path] = None,
        interval_seconds: int = DEFAULT_TASK_DRAIN_INTERVAL_SECONDS,
        max_tasks: int = 10,
        org_filter: Optional[str] = None,
        **_kwargs: Any,
    ):
        from core.platform.state import PlatformStateManager

        self._psm = PlatformStateManager(platform_home)
        self.platform_home = self._psm.platform_home
        self._interval = max(30, interval_seconds)
        self._max_tasks = max_tasks
        self._org_filter = org_filter
        self._running = False
        self._cycle_count = 0
        self._status = STATUS_STOPPED
        self._gate = RateLimitGate()
        self._governor = QuotaGovernor()
        self._log_path = self.platform_home / "task_drain_log.jsonl"

    async def start(self) -> None:
        self._running = True
        logger.info("TaskDrainScheduler started (interval=%ds)", self._interval)
        try:
            while self._running:
                self._beat(STATUS_RUNNING)
                if self._gate.current() is not None:
                    await self._pause_until_reset()
                    continue
                await self.run_cycle()
                if self._gate.current() is not None:
                    continue
                # interval をチャンク分割して stop() に即応する
                waited = 0.0
                while self._running and waited < self._interval:
                    self._beat(STATUS_RUNNING)
                    chunk = min(PAUSE_SLEEP_CHUNK_SECONDS, self._interval - waited)
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
        """1 サイクル: PENDING タスクを着火する。クォータ逼迫時はスキップ。"""
        self._cycle_count += 1
        started = _now_iso()

        # 新規タスクの着火は実作業（claude セッション）を生むので、background クォータが
        # 逼迫している間はスキップする（トレンド daemon と同じ思想）。
        if not self._governor.allow(PRIORITY_BACKGROUND).allowed:
            summary = {
                "cycle": self._cycle_count,
                "started_at": started,
                "skipped_by_quota": True,
            }
            self._write_log(summary)
            return summary

        from core.runtime.task_drain import drain_pending_tasks

        fired = 0
        failed = 0
        try:
            results = await drain_pending_tasks(
                org_filter=self._org_filter, max_tasks=self._max_tasks
            )
            for r in results:
                if isinstance(r, dict) and r.get("session_id"):
                    fired += 1
                elif isinstance(r, dict) and r.get("error"):
                    failed += 1
        except Exception as exc:  # noqa: BLE001 - drain ループは決して落とさない
            logger.info("task drain failed: %s", exc)
            failed += 1

        summary = {
            "cycle": self._cycle_count,
            "started_at": started,
            "completed_at": _now_iso(),
            "fired": fired,
            "failed": failed,
        }
        self._write_log(summary)
        return summary

    async def _pause_until_reset(self) -> None:
        info = self._gate.current()
        now = datetime.now(timezone.utc)
        reset_at = (info.reset_at if info else None) or (now + DEFAULT_BACKOFF)
        reset_at = min(max(reset_at, now), now + MAX_BACKOFF)
        self._beat(STATUS_PAUSED_RATE_LIMIT)
        while self._running:
            remaining = (reset_at - datetime.now(timezone.utc)).total_seconds()
            if remaining <= 0:
                break
            self._beat(STATUS_PAUSED_RATE_LIMIT)
            await asyncio.sleep(min(PAUSE_SLEEP_CHUNK_SECONDS, remaining))

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

    def get_recent_logs(self, n: int = 20) -> list[Dict[str, Any]]:
        if not self._log_path.exists():
            return []
        lines = self._log_path.read_text(encoding="utf-8").strip().splitlines()
        out = []
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out
