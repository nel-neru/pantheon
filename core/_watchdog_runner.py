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
    from core.runtime.daemon_registry import pid_path

    home = Path(get_platform_home())
    home.mkdir(parents=True, exist_ok=True)
    # pythonw（コンソールなし）起動が前提なので stdout ではなくファイルへ記録する。
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler(home / "watchdog.log", encoding="utf-8")],
    )
    log = logging.getLogger(__name__)

    from core.runtime.watchdog import WatchdogRunner, acquire_single_instance_lock

    # 単一インスタンスは OS 排他ロックで保証する（pid ファイル比較は ONLOGON＋
    # ガードタスク同時発火の TOCTOU と、再起動後の PID 再利用誤判定に弱い）。
    # ロックはプロセス終了時に OS が必ず解放するため、クラッシュ後の再起動も妨げない。
    lock = acquire_single_instance_lock(home)
    if lock is None:
        log.info("watchdog already running (lock held) — exiting")
        return

    # pid ファイルは status 表示（pantheon daemons status / API）用に併記する。
    # 原子的に書く（書き込み中クラッシュで partial pid を残し cleanup チェックを誤らせない）。
    from core.persistence import atomic_write_text

    pid_file = pid_path("watchdog")
    atomic_write_text(pid_file, str(os.getpid()))

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
        lock.close()


if __name__ == "__main__":
    main()
