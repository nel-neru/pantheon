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
from typing import Any


def coerce_int(value: Any, default: int = 0) -> int:
    """raw な永続 JSON 由来の値を安全に int 化する（null/非数値は ``default`` へ倒す）。

    disk から生 JSON で読まれた dict は legacy/手編集/外部生成で値が ``null`` や非数値
    文字列になりうる。``int(None)``/``int("high")`` はソートキーやメトリクス算出中に
    TypeError/ValueError を送出し、try/except に包まれた 24/7 デーモンの drain ループ等を
    **静かに止める**（[[get-default-none-footgun]]）。

    **重要**: ``0`` は有効値なので ``value or default`` は使えない（``0 or 5 == 5`` で 0 を
    破壊する）。``is None`` ＋ try/except で coerce すること。書き込み側の原子性
    （``atomic_write_text``）と対になる、読み取り側の防御ヘルパ。
    """
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def coerce_float(value: Any, default: float = 0.0) -> float:
    """raw な永続 JSON 由来の値を安全に float 化する（null/非数値は ``default`` へ倒す）。

    quality_score / reach / revenue 等の数値メトリクスも disk の生 JSON 由来で ``null``/
    非数値になりうる。``float(None)`` は昇格判定や handoff 推奨の算出を丸ごと落とす。
    ``coerce_int`` と対の ``is None`` ＋ try/except で coerce する。
    """
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def coerce_sort_str(value: Any) -> str:
    """raw な永続 JSON 由来の値を比較安全な str へ coerce する（null/非 str を空文字へ）。

    created_at/timestamp 等のソートキーが ``null`` だと ``None < str`` の TypeError で
    ソート全体が落ちる。``str(value) if value else ""`` で null/falsy を ""、非 str を
    文字列化して比較を安全化する。
    """
    return str(value) if value else ""


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
