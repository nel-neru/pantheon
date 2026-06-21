"""ハンズオフ運用: `pantheon story produce` を Windows タスクスケジューラで毎日自動実行する。

コマンド構築は純粋関数（テスト可能）。実登録は ``schtasks`` を ``runner`` 経由で呼ぶ（注入可能）。
スケジュール実行するのは produce（brief→render＝外部副作用なし）。外部公開（YouTube）は人間の
``story publish --yes`` に残すので、無人実行でも誤公開はしない。Windows 専用（schtasks）。
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional, Tuple

Runner = Callable[[List[str]], Tuple[int, str]]


def _slug(org: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", org).strip("-")
    if not org.isascii() or not s:
        digest = hashlib.sha1(org.encode("utf-8")).hexdigest()[:8]
        s = f"{s}-{digest}" if s else f"org-{digest}"
    return s or "org"


def task_name_for(org: str) -> str:
    """会社ごとに一意なタスク名（非ASCII名は短いハッシュで衝突回避）。"""
    return f"Pantheon Story Produce - {_slug(org)}"


def _main_py() -> str:
    from core.paths import resource_root

    return str(Path(resource_root()) / "main.py")


def build_create_command(
    org: str,
    *,
    count: int = 1,
    time: str = "09:00",
    python_exe: Optional[str] = None,
    main_py: Optional[str] = None,
) -> List[str]:
    """毎日 ``story produce`` を実行する schtasks /Create の argv を組み立てる（純粋）。"""
    py = python_exe or sys.executable
    script = main_py or _main_py()
    tr = f'"{py}" "{script}" story produce --org "{org}" --count {int(count)}'
    return [
        "schtasks", "/Create",
        "/TN", task_name_for(org),
        "/TR", tr,
        "/SC", "DAILY",
        "/ST", time,
        "/F",
    ]  # fmt: skip


def build_delete_command(org: str) -> List[str]:
    return ["schtasks", "/Delete", "/TN", task_name_for(org), "/F"]


def build_query_command(org: str) -> List[str]:
    return ["schtasks", "/Query", "/TN", task_name_for(org)]


def _default_runner(cmd: List[str]) -> Tuple[int, str]:
    from core.runtime.process_utils import no_window_kwargs

    proc = subprocess.run(
        cmd, capture_output=True, encoding="utf-8", errors="replace", **no_window_kwargs()
    )
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or ""))


def _is_windows() -> bool:
    return os.name == "nt"


def install_schedule(
    org: str,
    *,
    count: int = 1,
    time: str = "09:00",
    python_exe: Optional[str] = None,
    main_py: Optional[str] = None,
    runner: Optional[Runner] = None,
) -> Tuple[bool, str]:
    """毎日タスクを登録する。Windows 以外は正直に未対応を返す。"""
    if not _is_windows():
        return False, "定期実行は Windows のタスクスケジューラ専用です（schtasks）。"
    cmd = build_create_command(org, count=count, time=time, python_exe=python_exe, main_py=main_py)
    code, out = (runner or _default_runner)(cmd)
    return code == 0, out.strip()


def uninstall_schedule(org: str, *, runner: Optional[Runner] = None) -> Tuple[bool, str]:
    if not _is_windows():
        return False, "Windows 専用です。"
    code, out = (runner or _default_runner)(build_delete_command(org))
    return code == 0, out.strip()


def schedule_status(org: str, *, runner: Optional[Runner] = None) -> Tuple[bool, str]:
    if not _is_windows():
        return False, "Windows 専用です。"
    code, out = (runner or _default_runner)(build_query_command(org))
    return code == 0, out.strip()
