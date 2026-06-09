"""同梱リソースのパス解決（exe 化 / 通常実行の両対応）。

Pantheon は通常 `pip install -e .` したソースから動くが、PyInstaller で
exe 化（frozen）すると、同梱した読み取り専用リソース（`web/dist`, `config`,
`skills`, `knowledge`, `agents/definitions`, ソースツリー等）は `sys._MEIPASS`
配下に展開される。両方の実行形態で正しいパスを返すための単一の入口を提供する。

重要な区別:
- 同梱の *読み取り専用リソース* は `resource_path()` で解決する。
- *ユーザー状態*（`~/.pantheon`）は frozen でも変わらないので、ここでは扱わない
  （`core.platform.state.get_platform_home` / `Path.home()` をそのまま使う）。
"""

from __future__ import annotations

import sys
from pathlib import Path

# このファイルは <repo root>/core/paths.py に置かれる前提。
# core/paths.py -> core -> <repo root>
_SOURCE_ROOT = Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    """PyInstaller 等で凍結（exe 化）された状態かどうかを返す。"""
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """同梱された読み取り専用リソースのルートディレクトリを返す。

    - 通常実行: リポジトリルート（このモジュールの2つ上）。
    - frozen (PyInstaller): ``sys._MEIPASS``（onedir は ``_internal``、
      onefile は一時展開先）。
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return _SOURCE_ROOT


def resource_path(*parts: str) -> Path:
    """``resource_root()`` を基準に同梱リソースへの絶対パスを組み立てる。

    例: ``resource_path("web", "dist")`` / ``resource_path("config", "default.yaml")``
    """
    return resource_root().joinpath(*parts)
