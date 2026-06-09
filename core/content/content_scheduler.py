"""ContentScheduler — ContentJob を定期実行する PDCA ループ。

各サイクル: 期限が来たジョブを実行（投稿 content_asset 提案を生成＝Plan/Do）→ 成果由来の構造介入を
提案（Act: ``HQInterventionProposer.propose_all``）。Claude のレート制限を検知したらループを安全に
自動停止する（「レート制限になるまで無限に実行」の実体）。状態は ``content_scheduler_state.json`` に
永続化し、Web/CLI から参照できる。外部公開は一切しない。
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

logger = logging.getLogger(__name__)

DEFAULT_CONTENT_INTERVAL_SECONDS = 600


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ContentScheduler:
    """コンテンツ生成ジョブの定期ランナー（レート制限で自動停止）。"""

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
                stop = await self.run_cycle()
                if stop:
                    # レート制限を検知 → 自律的にループ停止（再開はユーザー操作 or 次回 start）。
                    logger.info(
                        "ContentScheduler self-stopped due to rate limit (retry_at=%s)",
                        self._retry_at,
                    )
                    break
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            self._write_state(running=False)

    def stop(self) -> None:
        self._running = False

    async def run_cycle(self) -> bool:
        """1サイクル実行。レート制限を検知したら True（ループ停止）。"""
        self._cycle_count += 1
        started = _now_iso()
        due = self._store.due_jobs()
        results: List[Dict[str, Any]] = []
        rate_limited = False

        for job in due:
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

        # 投稿処理: 承認済みで予約時刻に達した PublishJob のうち auto モードのみを実行する。
        # assisted モードは人間が最終送信する前提なので daemon は自動発火しない（投稿ゲート尊重）。
        published = 0
        if not rate_limited:
            published = await self._process_due_publish_jobs()

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
            "published": published,
            "interventions": interventions,
            "rate_limited": rate_limited,
            "retry_at": self._retry_at,
            "results": results,
        }
        self._write_log(summary)
        self._write_state(running=self._running and not rate_limited)
        return rate_limited

    async def _process_due_publish_jobs(self) -> int:
        """予約時刻に達した auto モードの PublishJob を実行し、成功件数を返す。

        assisted モードは人間が最終送信するため対象外。失敗（ブラウザ未接続等）は
        ジョブ status=failed になり再ループしない。例外は握りつぶしてサイクルを壊さない。
        """
        try:
            from core.publishing.base import PUBLISH_MODE_AUTO
            from core.publishing.publish_jobs import PublishJobStore
            from core.publishing.runner import run_publish_job
        except ImportError:
            return 0

        published = 0
        try:
            pub_store = PublishJobStore(platform_home=self.platform_home)
            for pjob in pub_store.due_jobs():
                if pjob.mode != PUBLISH_MODE_AUTO:
                    continue
                res = await run_publish_job(
                    pjob, store=pub_store, platform_home=self.platform_home, dry_run=False
                )
                if res.get("ok"):
                    published += 1
        except Exception:  # noqa: BLE001 — 投稿処理の失敗でサイクル全体を壊さない
            return published
        return published

    # ---- 状態・ログ ----
    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "rate_limited": self._rate_limited,
            "retry_at": self._retry_at,
            "cycle_count": self._cycle_count,
            "interval_seconds": self._interval,
        }

    def _write_state(self, *, running: bool) -> None:
        state = {
            "running": running,
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
