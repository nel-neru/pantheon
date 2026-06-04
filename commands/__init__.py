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
  export ANTHROPIC_API_KEY=sk-ant-...   # Claude API キー（初回のみ）
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
    modules: list[ModuleType] = []
    for module_info in sorted(pkgutil.iter_modules(__path__), key=lambda item: item.name):
        if module_info.name.startswith("_") or module_info.name in _EXCLUDED_MODULES:
            continue
        modules.append(importlib.import_module(f"{__name__}.{module_info.name}"))
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
