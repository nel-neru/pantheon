"""Daemon registry — the single source of truth for Pantheon's long-lived daemons.

Previously the spawn/stop/status logic for the improvement daemon and the
content daemon was duplicated across ``web/server.py`` and
``commands/platform.py``. This module centralises it:

* :data:`KNOWN_DAEMONS` — every daemon's spec (runner module, pid/log files,
  frozen-exe restart flag, default interval)
* :func:`spawn_daemon` / :func:`stop_daemon` / :func:`daemon_status`
* desired state (``enabled.json``) — which daemons *should* be running, with
  which args. The watchdog (A-3) reconciles reality against this after
  crashes and PC reboots; ``stop`` flips it off so the watchdog never fights
  an operator's explicit stop.

File layout (under ``~/.pantheon``): pid/log filenames are kept identical to
the pre-registry layout for backward compatibility; desired state and
heartbeats live under ``~/.pantheon/daemons/``.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from core.paths import resource_root
from core.runtime.heartbeat import (
    heartbeat_age_seconds,
    read_heartbeat,
    stale_threshold_seconds,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = resource_root()
ENABLED_FILENAME = "enabled.json"


@dataclass(frozen=True)
class DaemonSpec:
    """Static description of one managed daemon."""

    name: str
    description: str
    runner_module: str  # `python -m <module>` entry
    frozen_flag: str  # Pantheon.exe self-restart flag (see main.py)
    default_interval: int
    pid_filename: str
    log_filename: str


# 新しいデーモンを足すときは KNOWN_DAEMONS への追加に加えて以下も更新する:
#   - commands/daemons.py の DAEMON_NAMES（argparse choices・同期必須）
#   - main.py の frozen 自己再起動エントリ（frozen_flag と一致させる）
#   - tests/test_daemon_registry.py::test_known_daemons_and_get_spec（set 等値ピン）
#   - tests/test_web_server.py::test_daemons_status_lists_registry（名前リスト等値ピン）
# watchdog / web の status / CLI の _resolve_names は KNOWN_DAEMONS を自動列挙するため追加登録は不要。
KNOWN_DAEMONS: Dict[str, DaemonSpec] = {
    "improvement": DaemonSpec(
        name="improvement",
        description="自律改善ループ（イベント検知→提案→Policy判定→自動適用）",
        runner_module="core._daemon_runner",
        frozen_flag="--daemon-run",
        default_interval=3600,
        pid_filename="daemon.pid",
        log_filename="daemon.log",
    ),
    "content": DaemonSpec(
        name="content",
        description="コンテンツ/PDCA ループ（ContentJob 実行・auto 予約投稿・構造介入提案）",
        runner_module="core._content_daemon_runner",
        frozen_flag="--content-daemon-run",
        default_interval=600,
        pid_filename="content_daemon.pid",
        log_filename="content_daemon.log",
    ),
    "watchdog": DaemonSpec(
        name="watchdog",
        description="daemon 監視・自動復旧（enabled.json と実態の突合、ハング検知・再起動）",
        runner_module="core._watchdog_runner",
        frozen_flag="--watchdog-run",
        default_interval=60,
        pid_filename="watchdog.pid",
        log_filename="watchdog.log",
    ),
    "trend": DaemonSpec(
        name="trend",
        description="トレンド収集→採点→人間承認ゲート付き ContentJob/新規事業提案への変換",
        runner_module="core._trend_daemon_runner",
        frozen_flag="--trend-daemon-run",
        default_interval=6 * 3600,
        pid_filename="trend_daemon.pid",
        log_filename="trend_daemon.log",
    ),
    "revenue": DaemonSpec(
        name="revenue",
        description="収益分析＋ポートフォリオ提案の定期スキャン（LLM 非依存・承認ゲート付き・AUTO-1）",
        runner_module="core._revenue_daemon_runner",
        frozen_flag="--revenue-daemon-run",
        default_interval=24 * 3600,
        pid_filename="revenue_daemon.pid",
        log_filename="revenue_daemon.log",
    ),
}


def get_spec(name: str) -> DaemonSpec:
    spec = KNOWN_DAEMONS.get(name)
    if spec is None:
        raise ValueError(f"unknown daemon '{name}' (known: {', '.join(sorted(KNOWN_DAEMONS))})")
    return spec


def _home(platform_home: Optional[Path]) -> Path:
    if platform_home is not None:
        return Path(platform_home)
    from core.platform.state import get_platform_home

    return Path(get_platform_home())


def pid_path(name: str, *, platform_home: Optional[Path] = None) -> Path:
    return _home(platform_home) / get_spec(name).pid_filename


def log_path(name: str, *, platform_home: Optional[Path] = None) -> Path:
    return _home(platform_home) / get_spec(name).log_filename


def read_pid(name: str, *, platform_home: Optional[Path] = None) -> Optional[int]:
    path = pid_path(name, platform_home=platform_home)
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def build_command(spec: DaemonSpec, extra_args: Sequence[str] = ()) -> List[str]:
    """Argv for the daemon subprocess (frozen-exe aware, pure/testable)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, spec.frozen_flag, *extra_args]
    return [sys.executable, "-m", spec.runner_module, *extra_args]


# --------------------------------------------------------------------------- #
# Desired state (enabled.json) — what the watchdog should keep alive
# --------------------------------------------------------------------------- #
def _enabled_path(platform_home: Optional[Path]) -> Path:
    return _home(platform_home) / "daemons" / ENABLED_FILENAME


def load_enabled(*, platform_home: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """``{name: {"enabled": bool, "args": [...]}}`` — missing file means empty."""
    path = _enabled_path(platform_home)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for name, entry in data.items():
        if isinstance(entry, dict):
            raw_args = entry.get("args", [])
            out[str(name)] = {
                "enabled": bool(entry.get("enabled")),
                "args": [str(a) for a in raw_args if isinstance(a, (str, int))]
                if isinstance(raw_args, list)
                else [],
            }
    return out


def set_enabled(
    name: str,
    enabled: bool,
    *,
    args: Optional[Sequence[str]] = None,
    platform_home: Optional[Path] = None,
) -> None:
    """Persist the desired state for one daemon (atomic read-modify-write)."""
    get_spec(name)  # validate
    path = _enabled_path(platform_home)
    state = load_enabled(platform_home=platform_home)
    entry = state.get(name, {"enabled": False, "args": []})
    entry["enabled"] = enabled
    if args is not None:
        entry["args"] = list(args)
    state[name] = entry
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(state, ensure_ascii=False, indent=2))
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError as exc:
        logger.warning("failed to persist daemon desired state: %s", exc)


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
def spawn_daemon(
    name: str,
    *,
    args: Sequence[str] = (),
    platform_home: Optional[Path] = None,
    record_enabled: bool = True,
) -> Dict[str, Any]:
    """Start a daemon subprocess (no-op if already running).

    Returns ``{"status": "started"|"already_running", "pid": int, "log_path": str}``.
    ``record_enabled`` updates the desired state so the watchdog restores the
    daemon with the same args after a crash or reboot (the watchdog itself
    passes ``record_enabled=False`` to avoid rewriting what it reads).
    """
    spec = get_spec(name)
    pid_file = pid_path(name, platform_home=platform_home)
    log_file = log_path(name, platform_home=platform_home)

    pid = read_pid(name, platform_home=platform_home)
    if pid is not None and is_process_running(pid):
        if record_enabled:
            set_enabled(name, True, args=args, platform_home=platform_home)
        return {"status": "already_running", "pid": pid, "log_path": str(log_file)}
    if pid is not None:
        pid_file.unlink(missing_ok=True)

    pid_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_command(spec, args)
    with log_file.open("a", encoding="utf-8") as log_handle:
        proc = subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_file.write_text(str(proc.pid), encoding="utf-8")
    if record_enabled:
        set_enabled(name, True, args=args, platform_home=platform_home)
    logger.info("daemon '%s' started (pid=%s)", name, proc.pid)
    return {"status": "started", "pid": proc.pid, "log_path": str(log_file)}


def stop_daemon(
    name: str,
    *,
    platform_home: Optional[Path] = None,
    record_enabled: bool = True,
) -> Dict[str, Any]:
    """Stop a daemon and (by default) flip its desired state off.

    Explicit stop = operator intent: the watchdog must not resurrect it.
    Returns ``{"status": "stopped"|"not_running"|"already_stopped", "pid": ...}``.
    """
    get_spec(name)
    pid_file = pid_path(name, platform_home=platform_home)
    log_file = log_path(name, platform_home=platform_home)
    if record_enabled:
        set_enabled(name, False, platform_home=platform_home)

    pid = read_pid(name, platform_home=platform_home)
    if pid is None:
        pid_file.unlink(missing_ok=True)
        return {"status": "not_running", "pid": None, "log_path": str(log_file)}
    try:
        os.kill(pid, signal.SIGTERM)
        status = "stopped"
    except OSError:
        status = "already_stopped"
    pid_file.unlink(missing_ok=True)
    logger.info("daemon '%s' %s (pid=%s)", name, status, pid)
    return {"status": status, "pid": pid, "log_path": str(log_file)}


def daemon_status(
    name: str,
    *,
    now: Optional[datetime] = None,
    platform_home: Optional[Path] = None,
) -> Dict[str, Any]:
    """One daemon's health: pid liveness × heartbeat freshness × desired state."""
    spec = get_spec(name)
    pid = read_pid(name, platform_home=platform_home)
    running = bool(pid is not None and is_process_running(pid))

    beat = read_heartbeat(name, platform_home=platform_home)
    age = heartbeat_age_seconds(name, now=now, platform_home=platform_home)
    interval = None
    if beat is not None:
        raw_interval = beat.get("interval_seconds")
        if isinstance(raw_interval, (int, float)) and raw_interval > 0:
            interval = float(raw_interval)
    threshold = stale_threshold_seconds(interval or spec.default_interval)
    heartbeat_stale = age is None or age > threshold

    desired = load_enabled(platform_home=platform_home).get(name, {})
    return {
        "name": name,
        "description": spec.description,
        "running": running,
        "pid": pid,
        "log_path": str(log_path(name, platform_home=platform_home)),
        "enabled": bool(desired.get("enabled", False)),
        "heartbeat": beat,
        "heartbeat_age_seconds": age,
        "heartbeat_stale": heartbeat_stale,
        # 生きているのに heartbeat が stale = ハング疑い（watchdog の restart 対象）
        "healthy": running and not heartbeat_stale,
    }


def all_statuses(
    *, now: Optional[datetime] = None, platform_home: Optional[Path] = None
) -> List[Dict[str, Any]]:
    return [
        daemon_status(name, now=now, platform_home=platform_home) for name in sorted(KNOWN_DAEMONS)
    ]
