"""RevenueScheduler — periodic revenue intelligence + portfolio-proposal scan daemon.

Runs under the daemon registry as the ``revenue`` daemon (AUTO-1, Phase 5). Each
cycle it:

* reads recorded revenue (:meth:`OutcomeStore.revenue_by_month`) and computes a
  revenue analysis (:func:`analyze_revenue` — MoM / trend / next-month forecast),
* when a positive monthly ``target`` is configured, scans for portfolio proposals
  (:func:`scan_portfolio_proposals`) and enqueues them on the **approval gate**
  (idempotent; never auto-adopted).

Both steps are **LLM-non-dependent / pure** (no ``claude`` subprocess), so — unlike
the trend/content daemons — this daemon does **not** consult the rate-limit gate
or quota governor: there is no token to throttle, and gating it would needlessly
pause work that costs nothing. It only emits a heartbeat like the other daemons so
the watchdog can detect a hang.

When ``target <= 0`` the proposal side is idle (the daemon still logs the revenue
analysis). Enabling the daemon without a target therefore does nothing harmful;
setting ``--target N`` activates approval-gated proposal generation. This is the
safe, reversible default for unattended (24/7) operation.
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

HEARTBEAT_NAME = "revenue"
DEFAULT_REVENUE_INTERVAL_SECONDS = 24 * 3600  # 日次
STOP_POLL_CHUNK_SECONDS = 60.0  # interval をこの粒度で分割し stop() に即応する

STATUS_RUNNING = "running"
STATUS_STOPPED = "stopped"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RevenueScheduler:
    """収益分析＋ポートフォリオ提案スキャンを定期実行する daemon（LLM 非依存・トークン消費ゼロ）。"""

    def __init__(
        self,
        platform_home: Optional[Path] = None,
        interval_seconds: int = DEFAULT_REVENUE_INTERVAL_SECONDS,
        target: float = 0.0,
        source_org_name: str = "HQ",
        min_reach: float = 0.0,
        **_kwargs: Any,
    ):
        from core.platform.state import PlatformStateManager

        self._psm = PlatformStateManager(platform_home)
        self.platform_home = self._psm.platform_home
        self._interval = max(60, interval_seconds)
        self._target = float(target)
        self._source_org_name = source_org_name
        self._min_reach = float(min_reach)
        self._running = False
        self._cycle_count = 0
        self._status = STATUS_STOPPED
        self._log_path = self.platform_home / "revenue_scheduler_log.jsonl"

    async def start(self) -> None:
        self._running = True
        logger.info(
            "RevenueScheduler started (interval=%ds, target=%.2f)", self._interval, self._target
        )
        try:
            while self._running:
                self._beat(STATUS_RUNNING)
                await self.run_cycle()
                # interval をチャンク分割して stop() に即応する
                waited = 0.0
                while self._running and waited < self._interval:
                    self._beat(STATUS_RUNNING)
                    chunk = min(STOP_POLL_CHUNK_SECONDS, self._interval - waited)
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
        """1 サイクル: 収益分析（常時）＋ target>0 ならポートフォリオ提案を承認ゲートへ起票。"""
        self._cycle_count += 1
        started = _now_iso()

        from core.metrics.outcomes import OutcomeStore
        from core.metrics.revenue_intelligence import analyze_revenue

        analysis: Dict[str, Any] = {}
        try:
            store = OutcomeStore(platform_home=self.platform_home)
            by_month = store.revenue_by_month(None)
            analysis = analyze_revenue(by_month)
        except Exception as exc:  # noqa: BLE001
            logger.info("revenue analysis failed: %s", exc)

        scan: Dict[str, Any] = {}
        if self._target > 0:
            try:
                from core.hierarchy.portfolio_pipeline import scan_portfolio_proposals

                scan = scan_portfolio_proposals(
                    target=self._target,
                    platform_home=self.platform_home,
                    source_org_name=self._source_org_name,
                    min_reach=self._min_reach,
                )
            except Exception as exc:  # noqa: BLE001
                logger.info("portfolio proposal scan failed: %s", exc)

        summary = {
            "cycle": self._cycle_count,
            "started_at": started,
            "completed_at": _now_iso(),
            "target": self._target,
            "trend": analysis.get("trend"),
            "forecast_next": analysis.get("forecast_next"),
            "proposals": scan.get("proposals", 0),
            "scanned": scan.get("scanned", 0),
            "scan_skipped": self._target <= 0,
        }
        self._write_log(summary)
        return summary

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "status": self._status,
            "cycle_count": self._cycle_count,
            "interval_seconds": self._interval,
            "target": self._target,
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
