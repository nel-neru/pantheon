#!/usr/bin/env python3
"""
GUIページのテストカバレッジをチェックするスクリプト。
pages/*.tsx に対応する __tests__/*.test.tsx が存在するか確認する。
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = REPO_ROOT / "web" / "frontend" / "src" / "pages"
TESTS_DIR = PAGES_DIR / "__tests__"


def check_coverage() -> int:
    page_files = [f for f in PAGES_DIR.glob("*.tsx") if not f.name.startswith("_")]

    missing = []
    for page_file in sorted(page_files):
        stem = page_file.stem  # e.g. "ChatPage"
        test_file = TESTS_DIR / f"{stem}.test.tsx"
        if not test_file.exists():
            missing.append((page_file.name, test_file.name))

    if missing:
        print("テストファイルが不足しています:")
        for page, test in missing:
            print(f"  {page} -> {test} (missing)")
        print(f"\n{len(missing)} 件のテストが未作成です。")
        print("web/frontend/TESTING.md を参照してテストを追加してください。")
        return 1

    print(f"すべての GUI ページにテストが存在します ({len(page_files)} ページ確認済み)。")
    return 0


def check_help_warnings() -> list[str]:
    check_help_script = Path(__file__).parent / "check_help_coverage.py"
    if not check_help_script.exists():
        return []

    spec = importlib.util.spec_from_file_location("check_help", check_help_script)
    if spec is None or spec.loader is None:
        return ["警告: check_help_coverage.py の読み込みに失敗しました"]

    check_help = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check_help)
    return check_help.check_help_coverage()


def main() -> int:
    exit_code = check_coverage()

    help_warnings = check_help_warnings()
    if help_warnings:
        print()
        print("ヘルプページの警告:")
        for warning in help_warnings:
            print(f"  {warning}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
