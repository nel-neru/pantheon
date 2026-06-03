"""
io_utils — 原子的ファイル書き込み（D4/D5）

状態・提案・設定などの永続化はクラッシュ時の破損を避けるため、一時ファイルへ書いてから
`os.replace`（同一ファイルシステム内では原子的）で置換する。これにより「書き込み途中の
torn write」を防ぐ。複数プロセスが同じファイルを書く場合も、最後の置換が原子的に勝つ。
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

__all__ = ["atomic_write_text"]


def atomic_write_text(path: Path | str, text: str, encoding: str = "utf-8") -> None:
    """`path` にテキストを原子的に書き込む（tmp 書き込み → os.replace）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(text, encoding=encoding)
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(OSError):
            if tmp.exists():
                tmp.unlink()
