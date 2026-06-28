"""TrendScheduler — periodic trend collection + conversion daemon.

Runs under the daemon registry as the 4th daemon (``trend``). Each cycle, when
the quota governor allows background work, it collects trends (web + YouTube),
scores them, and converts the highest-scoring fresh ones into human-gated
ContentJob drafts and new-business proposals. Rate-limit aware (pauses with the
shared gate) and heartbeat-emitting like the other daemons.
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

HEARTBEAT_NAME = "trend"
DEFAULT_TREND_INTERVAL_SECONDS = 6 * 3600  # 6 時間ごと
PAUSE_SLEEP_CHUNK_SECONDS = 60.0

STATUS_RUNNING = "running"
STATUS_PAUSED_RATE_LIMIT = "paused_rate_limit"
STATUS_STOPPED = "stopped"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TrendScheduler:
    """トレンド収集→変換を定期実行する daemon（background 優先度、レート制限対応）。"""

    def __init__(
        self,
        platform_home: Optional[Path] = None,
        interval_seconds: int = DEFAULT_TREND_INTERVAL_SECONDS,
        min_score: float = 7.0,
        grok_enabled: bool = False,
        **_kwargs: Any,
    ):
        from core.platform.state import PlatformStateManager

        self._psm = PlatformStateManager(platform_home)
        self.platform_home = self._psm.platform_home
        self._interval = max(60, interval_seconds)
        self._min_score = min_score
        # Grok ブラウザ自動操作 collector を毎サイクルに含めるか（既定オフ・opt-in）。
        # 有効でも未接続/失効時は collect 側が捏造せず grok_needs_reconnect を返すだけ。
        self._grok_enabled = grok_enabled
        self._running = False
        self._cycle_count = 0
        self._status = STATUS_STOPPED
        self._gate = RateLimitGate()
        self._governor = QuotaGovernor()
        self._log_path = self.platform_home / "trend_scheduler_log.jsonl"

    async def start(self) -> None:
        self._running = True
        logger.info("TrendScheduler started (interval=%ds)", self._interval)
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
        """1 サイクル: 収集→採点→変換。クォータ逼迫時はスキップ。"""
        self._cycle_count += 1
        started = _now_iso()

        if not self._governor.allow(PRIORITY_BACKGROUND).allowed:
            summary = {
                "cycle": self._cycle_count,
                "started_at": started,
                "skipped_by_quota": True,
            }
            self._write_log(summary)
            return summary

        from core.trends.business_pipeline import scan_business_proposals
        from core.trends.runner import collect_and_store
        from core.trends.trend_to_jobs import convert_trends, propose_claude_code_updates
        from core.trends.untapped_genre import scan_untapped_genre_proposals

        collect = {}
        convert = {}
        cc = {}
        biz = {}
        untapped = {}
        try:
            # opt-in: grok を含めるときだけ sources を明示（既定は web+youtube のまま）。
            sources = {"web", "youtube", "grok"} if self._grok_enabled else None
            collect = await collect_and_store(platform_home=self.platform_home, sources=sources)
        except Exception as exc:  # noqa: BLE001
            logger.info("trend collect failed: %s", exc)
        try:
            convert = convert_trends(platform_home=self.platform_home, min_score=self._min_score)
        except Exception as exc:  # noqa: BLE001
            logger.info("trend convert failed: %s", exc)
        try:
            # Claude Code 自体のトレンド監視 → .claude/ 設定更新提案（承認ゲート付き）
            cc = propose_claude_code_updates(platform_home=self.platform_home)
        except Exception as exc:  # noqa: BLE001
            logger.info("cc trend monitoring failed: %s", exc)
        try:
            # 高スコアトレンド → 新規会社候補提案（承認ゲート付き・WIRE-B）
            biz = scan_business_proposals(
                platform_home=self.platform_home, min_score=self._min_score
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("business proposal scan failed: %s", exc)
        try:
            # 未開拓ジャンル → 新会社候補提案（承認ゲート付き・P4.2）
            untapped = scan_untapped_genre_proposals(
                platform_home=self.platform_home, min_score=self._min_score
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("untapped genre scan failed: %s", exc)

        summary = {
            "cycle": self._cycle_count,
            "started_at": started,
            "completed_at": _now_iso(),
            "collected": collect.get("collected", 0),
            "added": collect.get("added", 0),
            "grok": collect.get("grok", 0),
            # grok 有効時に未接続/失効を観測可能にする（捏造ゼロ・要再接続のシグナル）。
            "grok_needs_reconnect": collect.get("grok_needs_reconnect", False),
            "content_jobs": convert.get("content_jobs", 0),
            "proposals": convert.get("proposals", 0),
            # 変換の部分/全失敗を母数として残す（"新規ゼロ" と "全件失敗" を区別する）。
            "convert_failed": convert.get("failed", 0),
            "cc_proposals": cc.get("proposals", 0),
            "cc_failed": cc.get("failed", 0),
            "business_proposals": biz.get("proposals", 0),
            "untapped_genres": untapped.get("proposals", 0),
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
