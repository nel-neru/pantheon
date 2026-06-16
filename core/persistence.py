"""原子的なファイル永続化ヘルパ。

Pantheon の状態書き込みは「半端に書きかけた JSON」を絶対に残してはならない。
直接 ``path.write_text(...)`` で上書きすると、書き込み途中のクラッシュや、24h 自律
基盤で複数デーモンが同じファイルへ並行アクセスする競合で、ファイルが**切り詰められ**得る。
その破損ファイルは silent-drop 観測化（``warn_skipped_state_file``）が拾い「組織/提案が
音もなく消失した」というデータ消失として表面化する。

同じディレクトリ内の一時ファイルへ書いてから ``os.replace`` で原子的に差し替えることで、
読み手は常に「旧バイト列」か「新バイト列」のどちらかだけを見る（破れた書き込みを見ない）。
これは ``core/runtime/usage_gate.py`` 等が個別に実装していたパターンの共有版。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path | str, text: str, *, encoding: str = "utf-8") -> None:
    """``text`` を ``path`` へ原子的に書き込む。

    一時ファイルは ``path`` と同じディレクトリに作る（``os.replace`` が単一ファイル
    システム内の rename になり POSIX/Windows いずれでも原子的になる）。書き込みに
    失敗した場合は一時ファイルを掃除し、``path`` の既存内容には一切触れない。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        # 失敗時は半端な一時ファイルを残さない（孤児 .tmp を防ぐ）。元の path は無傷。
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
