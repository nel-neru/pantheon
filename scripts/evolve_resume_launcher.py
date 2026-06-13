r"""evolve_resume.ps1 をウィンドウ無し・フォーカスを奪わずに起動するランチャ。

問題: タスクスケジューラのアクションに `powershell -File evolve_resume.ps1` を
直接書くと、powershell.exe はコンソールサブシステムアプリのため毎時起動のたびに
コンソール窓が前面化し、フォーカス（とマウスカーソル）を奪う。全画面ゲーム中は
ゲームが裏画面へ落ちる。

解決: このランチャを `pythonw.exe`（GUI サブシステム＝窓を持たない。watchdog が
使うのと同じ windowless 実行体）から起動し、ここから powershell を
CREATE_NO_WINDOW で spawn する。これで窓もフラッシュも一切出ず、フォーカスも
奪われない。評価ロジック本体（heartbeat 判定・多重起動ガード・claude 再開）は
evolve_resume.ps1 のまま変更しない（このファイルは「隠して起動する」だけ）。

タスク登録: scripts/install_evolve_resume_task.ps1 が
    pythonw.exe scripts\evolve_resume_launcher.py <StaleMinutes>
を毎時タスクとして登録する。

使い方:  pythonw.exe scripts\evolve_resume_launcher.py [StaleMinutes]
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# CreateProcess の dwCreationFlags。子プロセス（powershell）に新しい可視コンソールを
# 一切作らせない（窓フラッシュ＝フォーカス奪取の根本原因を断つ）。
CREATE_NO_WINDOW = 0x08000000


def _log(msg: str) -> None:
    """evolve_resume.ps1 と同じログへ一行追記する（best-effort）。

    pythonw 配下はコンソールが無く、ここで未捕捉例外が出るとトレースバックは
    どこにも残らず Task Scheduler に汎用失敗としか映らない。spawn 失敗を
    観測可能にするため、ps1 と同じ ~/.pantheon/evolve_resume.log（ローカル時刻
    yyyy-MM-dd HH:mm:ss）に揃えて残す。"""
    try:
        ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        log_path = Path.home() / ".pantheon" / "evolve_resume.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{ts} {msg}\n")
    except Exception:
        pass  # ロギング自体の失敗で起動経路を壊さない。


def _powershell_path() -> str:
    """powershell.exe を解決する。タスクスケジューラ下では PATH が最小化される
    ことがあるため、PATH 解決に失敗したら System32 の既定パスへフォールバックする。"""
    found = shutil.which("powershell")
    if found:
        return found
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return str(Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")


def main(argv: list[str]) -> int:
    here = Path(__file__).resolve().parent
    repo = here.parent
    ps1 = here / "evolve_resume.ps1"
    if not ps1.exists():
        _log(f"launcher-error: evolve_resume.ps1 が見つかりません: {ps1}")
        return 1

    stale = argv[1] if len(argv) > 1 else "90"
    cmd = [
        _powershell_path(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ps1),
        "-StaleMinutes",
        str(stale),
    ]
    # evolve_resume.ps1 は claude を起動したら（待たずに）すぐ終わるため数秒で返る。
    # 戻り値を Task Scheduler の Last Run Result に正しく反映させるため待機する。
    try:
        proc = subprocess.run(cmd, creationflags=CREATE_NO_WINDOW, cwd=str(repo))
    except Exception as exc:  # noqa: BLE001 — 起動失敗を必ずログに残して観測可能にする
        _log(f"launcher-error: powershell の起動に失敗しました: {exc}")
        return 1
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
