"""Watchdog — keeps enabled daemons alive across crashes, hangs, and reboots.

Every poll (default 60s) the watchdog reconciles the **desired state**
(``enabled.json``, written by :mod:`core.runtime.daemon_registry`) against
reality (pid liveness × heartbeat freshness):

* enabled but dead          → start
* enabled, alive but the heartbeat is stale (hang) → kill + restart
* enabled and healthy       → nothing
* not enabled               → never touched (an operator's explicit stop wins)

Judging liveness by *heartbeat age* — not pid alone — is what lets a daemon
sit in a rate-limit pause for hours without being "rescued": paused daemons
keep beating (see ContentScheduler/_pause chunks), so they read as healthy.

Restarts are guarded two ways:
* exponential backoff per daemon (30s → 2m → 8m → cap 30m) so a crash-looping
  daemon cannot spin
* a post-spawn grace period (the stale threshold) so a *just-started* daemon
  is not immediately judged hung before its first heartbeat lands
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Dict, Optional

from core.runtime.daemon_registry import (
    KNOWN_DAEMONS,
    daemon_status,
    load_enabled,
    spawn_daemon,
    stop_daemon,
)
from core.runtime.heartbeat import stale_threshold_seconds, write_heartbeat

logger = logging.getLogger(__name__)

WATCHDOG_NAME = "watchdog"
DEFAULT_POLL_SECONDS = 60.0
BACKOFF_BASE_SECONDS = 30.0
BACKOFF_FACTOR = 4.0
BACKOFF_MAX_SECONDS = 1800.0

ACTION_NONE = "none"
ACTION_OK = "ok"
ACTION_START = "start"
ACTION_RESTART = "restart"

LOCK_FILENAME = "watchdog.lock"


def acquire_single_instance_lock(home: Path) -> Optional[IO[str]]:
    """watchdog の単一インスタンスを OS 排他ロックで保証する。

    pid ファイル比較は TOCTOU 競合（ONLOGON＋ガードタスクの同時発火）と
    再起動後の PID 再利用誤判定（無関係なプロセスを「watchdog 稼働中」と
    誤認して起動拒否）に弱いため、OS ロックを正とする。ロックはプロセス
    終了時に OS が必ず解放するので、クラッシュ後も次の起動を妨げない。

    Returns: ロックを保持するファイルハンドル（呼び出し側が生存期間中
    参照を保ち続けること）。取得失敗（既に稼働中）なら ``None``。
    """
    lock_path = Path(home) / LOCK_FILENAME
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(lock_path, "a+", encoding="utf-8")
    except OSError:
        return None
    try:
        if fh.tell() == 0 and not fh.read(1):
            # msvcrt.locking はロック範囲がデータを要求する場合があるため 1 byte 確保
            fh.write("x")
            fh.flush()
        fh.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:  # pragma: no cover - POSIX 環境のみ
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fh
    except OSError:
        fh.close()
        return None


def decide_action(
    *,
    enabled: bool,
    pid_alive: bool,
    heartbeat_stale: bool,
) -> str:
    """純関数: 1 daemon に対して watchdog が取るべきアクション。

    enabled でないものには一切触れない（kill もしない）— 手動運用を尊重する。
    """
    if not enabled:
        return ACTION_NONE
    if not pid_alive:
        return ACTION_START
    if heartbeat_stale:
        return ACTION_RESTART  # 生きているが heartbeat が途絶えた＝ハング疑い
    return ACTION_OK


def backoff_delay_seconds(attempts: int) -> float:
    """連続再起動試行回数に対する待機時間（30s → 2m → 8m → … cap 30m）。"""
    if attempts <= 0:
        return 0.0
    delay = BACKOFF_BASE_SECONDS * (BACKOFF_FACTOR ** (attempts - 1))
    return min(delay, BACKOFF_MAX_SECONDS)


@dataclass
class _DaemonGuard:
    """watchdog がメモリ内に持つ per-daemon の再起動管理状態。"""

    attempts: int = 0
    last_action_at: Optional[datetime] = None
    last_spawn_at: Optional[datetime] = None


@dataclass
class WatchdogRunner:
    poll_seconds: float = DEFAULT_POLL_SECONDS
    platform_home: Optional[Path] = None
    _running: bool = field(default=False, init=False)
    _guards: Dict[str, _DaemonGuard] = field(default_factory=dict, init=False)

    def stop(self) -> None:
        self._running = False

    async def run(self) -> None:
        self._running = True
        logger.info("watchdog started (poll=%ss)", self.poll_seconds)
        try:
            while self._running:
                try:
                    self.reconcile_once()
                except Exception:  # noqa: BLE001 - watchdog 自身は決して死なない
                    logger.exception("watchdog reconcile failed")
                write_heartbeat(
                    WATCHDOG_NAME,
                    {"status": "running", "interval_seconds": self.poll_seconds},
                    platform_home=self.platform_home,
                )
                await asyncio.sleep(self.poll_seconds)
        finally:
            self._running = False
            write_heartbeat(
                WATCHDOG_NAME,
                {"status": "stopped", "interval_seconds": self.poll_seconds},
                platform_home=self.platform_home,
            )
            logger.info("watchdog stopped")

    # ---- 1 回分の突合（テスト可能な単位） ----
    def reconcile_once(self, now: Optional[datetime] = None) -> Dict[str, str]:
        """desired state と実態を突合し、daemon ごとの実行アクションを返す。"""
        now = now or datetime.now(timezone.utc)
        actions: Dict[str, str] = {}
        enabled_map = load_enabled(platform_home=self.platform_home)

        for name, entry in enabled_map.items():
            if name == WATCHDOG_NAME or name not in KNOWN_DAEMONS:
                continue
            if not entry.get("enabled"):
                actions[name] = ACTION_NONE
                continue

            status = daemon_status(name, now=now, platform_home=self.platform_home)
            guard = self._guards.setdefault(name, _DaemonGuard())
            interval = None
            beat = status.get("heartbeat") or {}
            if isinstance(beat.get("interval_seconds"), (int, float)):
                interval = float(beat["interval_seconds"])
            threshold = stale_threshold_seconds(interval or KNOWN_DAEMONS[name].default_interval)

            # spawn 直後の grace: 初回 heartbeat が届く前に「ハング」と誤判定しない。
            in_grace = (
                guard.last_spawn_at is not None
                and (now - guard.last_spawn_at).total_seconds() < threshold
            )
            heartbeat_stale = bool(status["heartbeat_stale"]) and not in_grace

            action = decide_action(
                enabled=True,
                pid_alive=bool(status["running"]),
                heartbeat_stale=heartbeat_stale,
            )

            if action == ACTION_OK:
                # grace 中の「見かけ上の健康」では backoff をリセットしない
                # （spawn 直後に死ぬクラッシュループの抑制を維持する）。
                if not in_grace:
                    guard.attempts = 0
                actions[name] = action
                continue
            if action in (ACTION_START, ACTION_RESTART):
                delay = backoff_delay_seconds(guard.attempts)
                if (
                    guard.last_action_at is not None
                    and (now - guard.last_action_at).total_seconds() < delay
                ):
                    actions[name] = f"{action}_deferred"
                    continue
                if action == ACTION_RESTART:
                    logger.warning("daemon '%s' looks hung (heartbeat stale) — restarting", name)
                    stop_daemon(name, platform_home=self.platform_home, record_enabled=False)
                else:
                    logger.warning("daemon '%s' is down — starting", name)
                result = spawn_daemon(
                    name,
                    args=entry.get("args", []),
                    platform_home=self.platform_home,
                    record_enabled=False,
                )
                guard.attempts += 1
                guard.last_action_at = now
                guard.last_spawn_at = now
                logger.info(
                    "daemon '%s' %s -> %s (attempt %d)",
                    name,
                    action,
                    result.get("status"),
                    guard.attempts,
                )
            actions[name] = action
        return actions
