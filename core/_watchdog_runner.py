"""Pantheon - Watchdog Runner

Windows タスクスケジューラ（ONLOGON＋5分ガード）、`pantheon daemons start watchdog`、
または frozen exe の `Pantheon.exe --watchdog-run` から起動される。

単一インスタンスは pid ファイル（~/.pantheon/watchdog.pid）で保証するため、
5分ガードタスクが多重起動しても安全（既に生きていれば即終了する）。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# schtasks から `pythonw.exe <repo>\core\_watchdog_runner.py` と直接実行された場合、
# sys.path[0] は core/ になり `import core.*` が失敗するためリポジトリルートを補う。
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Pantheon Daemon Watchdog")
    # --interval は daemon_registry 経由（pantheon daemons start watchdog）の互換エイリアス
    parser.add_argument(
        "--poll", "--interval", dest="poll", type=float, default=60.0, help="突合間隔（秒）"
    )
    args = parser.parse_args()

    from core.platform.state import get_platform_home
    from core.runtime.daemon_registry import is_process_running, pid_path

    home = Path(get_platform_home())
    home.mkdir(parents=True, exist_ok=True)
    # pythonw（コンソールなし）起動が前提なので stdout ではなくファイルへ記録する。
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler(home / "watchdog.log", encoding="utf-8")],
    )
    log = logging.getLogger(__name__)

    pid_file = pid_path("watchdog")
    try:
        existing: int | None = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        existing = None
    if existing is not None and is_process_running(existing):
        log.info("watchdog already running (pid=%s) — exiting", existing)
        return
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    from core.runtime.watchdog import WatchdogRunner

    try:
        asyncio.run(WatchdogRunner(poll_seconds=args.poll).run())
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if pid_file.read_text(encoding="utf-8").strip() == str(os.getpid()):
                pid_file.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    main()
