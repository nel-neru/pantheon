from __future__ import annotations

import argparse
import importlib
import pkgutil
from types import ModuleType
from typing import Any

from .version import get_version_string

CLI_DESCRIPTION = "Pantheon — 自己成長型 AI Organization プラットフォーム"
CLI_EPILOG = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  使い方ガイド
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【クイックスタート（推奨: chatコマンド）】
  claude                                 # 一度ログイン（Pantheon は API キー不要・claude CLI を使用）
  pantheon init                          # 初回セットアップ（1回だけ）
  pantheon chat                          # あとは自然言語で話しかけるだけ！

  チャット例:
    > ECサイトを作りたい
    > MyApp のコードをレビューして
    > セキュリティの提案を全部承認して

【スラッシュコマンド（APIキー不要）】
  pantheon chat → /help でコマンド一覧を表示
"""

_EXCLUDED_MODULES = {"common"}


def discover_command_modules() -> list[ModuleType]:
    names = [module_info.name for module_info in pkgutil.iter_modules(__path__)]
    if not names:
        # exe 化（PyInstaller）時に pkgutil がサブモジュールを列挙できない場合の
        # フォールバック。同梱された commands/ ディレクトリの .py を直接走査する。
        from core.paths import resource_path

        commands_dir = resource_path("commands")
        if commands_dir.is_dir():
            names = [path.stem for path in commands_dir.glob("*.py")]

    modules: list[ModuleType] = []
    seen: set[str] = set()
    for name in sorted(names):
        if name.startswith("_") or name in _EXCLUDED_MODULES or name in seen:
            continue
        seen.add(name)
        modules.append(importlib.import_module(f"{__name__}.{name}"))
    return modules


def register_commands(subparsers: Any) -> None:
    for module in discover_command_modules():
        register = getattr(module, "register", None)
        if callable(register):
            register(subparsers)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=CLI_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=CLI_EPILOG,
    )
    parser.add_argument("-V", "--version", action="version", version=get_version_string())
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_commands(subparsers)
    return parser
