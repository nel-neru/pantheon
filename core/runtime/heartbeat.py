"""Daemon heartbeat files — freshness signals for the watchdog and health APIs.

Each long-lived daemon writes a small JSON heartbeat to
``~/.pantheon/daemons/<name>.heartbeat.json`` at every loop iteration *and*
during rate-limit pause chunks, so "alive but paused" is distinguishable from
"crashed". The watchdog (A-3) judges liveness by heartbeat age — never by pid
alone — which is what lets a paused daemon survive without being restarted.

All writes are atomic (tmp → ``os.replace``) and best-effort: a heartbeat
failure must never break the daemon loop it reports on.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

HEARTBEAT_DIRNAME = "daemons"
# 鮮度しきい値の下限。interval が極端に短い daemon でも誤 stale を避ける。
MIN_STALE_SECONDS = 180.0


def heartbeat_dir(platform_home: Optional[Path] = None) -> Path:
    if platform_home is None:
        from core.platform.state import get_platform_home

        platform_home = get_platform_home()
    return Path(platform_home) / HEARTBEAT_DIRNAME


def heartbeat_path(name: str, platform_home: Optional[Path] = None) -> Path:
    return heartbeat_dir(platform_home) / f"{name}.heartbeat.json"


def write_heartbeat(
    name: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    platform_home: Optional[Path] = None,
) -> None:
    """Atomically write a heartbeat. Best-effort — never raises."""
    record: Dict[str, Any] = {
        "name": name,
        "ts": datetime.now(timezone.utc).isoformat(),
        **(payload or {}),
    }
    path = heartbeat_path(name, platform_home)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False))
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError as exc:
        logger.debug("failed to write heartbeat for %s: %s", name, exc)


def read_heartbeat(name: str, *, platform_home: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    path = heartbeat_path(name, platform_home)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def heartbeat_age_seconds(
    name: str,
    *,
    now: Optional[datetime] = None,
    platform_home: Optional[Path] = None,
) -> Optional[float]:
    """Seconds since the last heartbeat, or ``None`` if absent/unparseable."""
    record = read_heartbeat(name, platform_home=platform_home)
    if record is None:
        return None
    raw_ts = record.get("ts")
    if not isinstance(raw_ts, str) or not raw_ts:
        return None
    try:
        ts = datetime.fromisoformat(raw_ts)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - ts).total_seconds())


def stale_threshold_seconds(interval_seconds: Optional[float]) -> float:
    """The freshness threshold for a daemon with the given loop interval."""
    if not interval_seconds or interval_seconds <= 0:
        return MIN_STALE_SECONDS
    return max(float(interval_seconds) * 3.0, MIN_STALE_SECONDS)


def is_stale(
    name: str,
    max_age_seconds: float,
    *,
    now: Optional[datetime] = None,
    platform_home: Optional[Path] = None,
) -> bool:
    """True when the heartbeat is missing or older than ``max_age_seconds``."""
    age = heartbeat_age_seconds(name, now=now, platform_home=platform_home)
    return age is None or age > max_age_seconds
