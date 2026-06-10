"""ContentScheduler — ContentJob を定期実行する PDCA ループ。

各サイクル: 期限が来たジョブを実行（投稿 content_asset 提案を生成＝Plan/Do）→ 成果由来の構造介入を
提案（Act: ``HQInterventionProposer.propose_all``）。Claude のレート制限を検知したらプロセスは
生かしたまま reset 時刻まで pause し、窓が開いたら自動 resume する（「制限解除されたら再開を
無限に繰り返す」の実体）。制限状態は :class:`RateLimitGate` 経由で全プロセス共有なので、別 daemon が
検知した制限でも先回りして pause する。状態は ``content_scheduler_state.json`` に永続化し、
Web/CLI から参照できる。外部公開は一切しない。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.content.content_jobs import ContentJobStore
from core.content.content_runner import run_content_job
from core.runtime.heartbeat import write_heartbeat
from core.runtime.rate_limit import DEFAULT_BACKOFF, MAX_BACKOFF
from core.runtime.usage_gate import RateLimitGate

HEARTBEAT_NAME = "content"  # core.runtime.daemon_registry の登録名と一致させる

logger = logging.getLogger(__name__)

DEFAULT_CONTENT_INTERVAL_SECONDS = 600
# pause 中の sleep チャンク。stop() への応答性と heartbeat の鮮度を保つ。
PAUSE_SLEEP_CHUNK_SECONDS = 60.0

STATUS_RUNNING = "running"
STATUS_PAUSED_RATE_LIMIT = "paused_rate_limit"
STATUS_STOPPED = "stopped"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ContentScheduler:
    """コンテンツ生成ジョブの定期ランナー（レート制限で pause → 自動 resume）。"""

    def __init__(
        self,
        platform_home: Optional[Path] = None,
        interval_seconds: int = DEFAULT_CONTENT_INTERVAL_SECONDS,
        run_pdca: bool = True,
        **_kwargs: Any,
    ):
        from core.platform.state import PlatformStateManager

        self._psm = PlatformStateManager(platform_home)
        self.platform_home = self._psm.platform_home
        self._store = ContentJobStore(self.platform_home)
        self._interval = max(1, interval_seconds)
        self._run_pdca = run_pdca
        self._running = False
        self._cycle_count = 0
        self._rate_limited = False
        self._retry_at: Optional[str] = None
        self._status = STATUS_STOPPED
        self._gate = RateLimitGate()
        self._log_path = self.platform_home / "content_scheduler_log.jsonl"
        self._state_path = self.platform_home / "content_scheduler_state.json"

    async def start(self) -> None:
        self._running = True
        self._rate_limited = False
        self._retry_at = None
        self._write_state(running=True)
        logger.info("ContentScheduler started (interval=%ds)", self._interval)
        try:
            while self._running:
                # 別プロセスが検知した制限も gate 経由で先回りして pause する。
                gate_info = self._gate.current()
                if gate_info is not None:
                    self._rate_limited = True
                    self._retry_at = gate_info.reset_at.isoformat() if gate_info.reset_at else None
                    await self._pause_until_reset()
                    continue
                limited = await self.run_cycle()
                if limited:
                    # レート制限を検知 → reset 時刻まで pause → 自動 resume（無限継続）。
                    await self._pause_until_reset()
                    continue
                if self._gate.current() is not None:
                    # サイクル中に gate へ報告された制限は interval を待たずに即 pause へ。
                    continue
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            self._write_state(running=False)

    def stop(self) -> None:
        self._running = False

    def _resume_at(self) -> datetime:
        """retry_at（ISO 文字列）から再開時刻を決める。欠損/不正時は既定バックオフ。"""
        now = datetime.now(timezone.utc)
        if self._retry_at:
            try:
                dt: Optional[datetime] = datetime.fromisoformat(self._retry_at)
            except ValueError:
                dt = None
            if dt is not None:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return min(max(dt, now), now + MAX_BACKOFF)
        return now + DEFAULT_BACKOFF

    async def _pause_until_reset(self) -> None:
        """レート制限の reset 時刻まで pause し、窓が開いたら自動 resume する。

        プロセスは生かしたまま短いチャンクで sleep する（``stop()`` への即応と
        heartbeat の鮮度維持のため）。resume 後は rate_limited 状態をクリアする。
        """
        resume_at = self._resume_at()
        logger.info("ContentScheduler paused (rate limit) — resumes at %s", resume_at.isoformat())
        self._write_state(running=True, status=STATUS_PAUSED_RATE_LIMIT)
        while self._running:
            remaining = (resume_at - datetime.now(timezone.utc)).total_seconds()
            if remaining <= 0:
                break
            # pause 中も heartbeat を打ち続ける（watchdog に「生きている」と伝える）。
            self._beat()
            await asyncio.sleep(min(PAUSE_SLEEP_CHUNK_SECONDS, remaining))
        if self._running:
            self._rate_limited = False
            self._retry_at = None
            self._write_state(running=True, status=STATUS_RUNNING)
            logger.info("ContentScheduler resumed after rate-limit window")

    async def run_cycle(self) -> bool:
        """1サイクル実行。レート制限を検知したら True（呼び出し側が pause する）。"""
        self._cycle_count += 1
        started = _now_iso()
        due = self._store.due_jobs()
        results: List[Dict[str, Any]] = []
        rate_limited = False

        for job in due:
            # ジョブ（claude 生成）は数分かかり得るので、1件ごとに heartbeat を更新し
            # 長いバッチ実行中に watchdog から「ハング」と誤判定されないようにする。
            self._beat()
            try:
                res = await run_content_job(job, self._psm)
            except Exception as exc:  # noqa: BLE001
                self._store.mark_run(job.job_id, status="error", detail=str(exc))
                results.append({"job_id": job.job_id, "status": "error", "detail": str(exc)})
                continue

            if res.get("status") == "rate_limited":
                rate_limited = True
                self._rate_limited = True
                self._retry_at = res.get("retry_at")
                # ジョブは未消化のまま（next_run_at を進めない）→ 再開時に再試行される。
                results.append({"job_id": job.job_id, **res})
                break

            self._store.mark_run(
                job.job_id, status=res.get("status", "done"), detail=res.get("detail", "")
            )
            results.append({"job_id": job.job_id, **res})

        # PDCA Act: 成果（reach>0/revenue<=0 等）に基づく構造介入提案（人間承認待ち）。
        interventions = 0
        if self._run_pdca and not rate_limited:
            try:
                from core.hierarchy.hq_interventions import HQInterventionProposer

                interventions = len(HQInterventionProposer(self._psm).propose_all())
            except Exception:  # noqa: BLE001 - 最小環境では無視
                interventions = 0

        summary = {
            "cycle": self._cycle_count,
            "started_at": started,
            "completed_at": _now_iso(),
            "due_jobs": len(due),
            "generated": sum(1 for r in results if r.get("status") == "generated"),
            "interventions": interventions,
            "rate_limited": rate_limited,
            "retry_at": self._retry_at,
            "results": results,
        }
        self._write_log(summary)
        # pause 中もプロセスは生きている（自動 resume する）ので running は落とさない。
        self._write_state(
            running=self._running,
            status=STATUS_PAUSED_RATE_LIMIT if rate_limited else None,
        )
        return rate_limited

    # ---- 状態・ログ ----
    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "status": self._status,
            "rate_limited": self._rate_limited,
            "retry_at": self._retry_at,
            "cycle_count": self._cycle_count,
            "interval_seconds": self._interval,
        }

    def _beat(self) -> None:
        """heartbeat を更新する（watchdog/health API 用、ベストエフォート）。"""
        write_heartbeat(
            HEARTBEAT_NAME,
            {
                "status": self._status,
                "cycle": self._cycle_count,
                "interval_seconds": self._interval,
                "rate_limited": self._rate_limited,
                "retry_at": self._retry_at,
            },
            platform_home=self.platform_home,
        )

    def _write_state(self, *, running: bool, status: Optional[str] = None) -> None:
        if status is None:
            status = STATUS_RUNNING if running else STATUS_STOPPED
        self._status = status
        state = {
            "running": running,
            "status": status,
            "rate_limited": self._rate_limited,
            "retry_at": self._retry_at,
            "cycle_count": self._cycle_count,
            "interval_seconds": self._interval,
            "updated_at": _now_iso(),
        }
        try:
            self._state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
        # 状態遷移は必ず heartbeat にも反映する（サイクルごとの生存通知を兼ねる）。
        self._beat()

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
        out = []
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out
