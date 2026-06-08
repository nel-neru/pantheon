#!/usr/bin/env python3
"""
ヘルプページカバレッジチェック。
src/pages/*.tsx（HelpPage以外）が存在する場合、
HelpPage.tsx でそのページへの言及があるかチェックする。
"""
import sys
from pathlib import Path

FRONTEND_PAGES_DIR = Path(__file__).parent.parent / "web/frontend/src/pages"
HELP_PAGE = FRONTEND_PAGES_DIR / "HelpPage.tsx"

# ページ名とHelpPage.tsxで言及されるべきキーワードのマッピング
# チャット/分析/ゴールの実行UIは wmux に集約したため GUI から削除済み（HelpPage の
# 「対話・実行（wmux）」節で言及）。ここには現存するページのみを列挙する。
PAGE_KEYWORDS = {
    "DashboardPage": ["プラットフォーム", "dashboard"],
    "OrgsPage": ["組織", "orgs"],
    "ProposalsPage": ["改善提案", "proposals"],
    "HandoffsPage": ["引き渡し", "handoff"],
    "AgentsPage": ["エージェント", "agents"],
    "AtlasPage": ["atlas"],
    "SessionsPage": ["セッション", "sessions"],
    "BoardPage": ["作業ボード", "board"],
    "DataPage": ["データ管理", "data"],
    "SettingsPage": ["設定", "settings"],
    "HelpPage": [],  # self-referential, skip
}


def check_help_coverage() -> list[str]:
    warnings = []

    if not HELP_PAGE.exists():
        return ["HelpPage.tsx が見つかりません"]

    help_content = HELP_PAGE.read_text(encoding="utf-8").lower()

    for page_file in sorted(FRONTEND_PAGES_DIR.glob("*.tsx")):
        page_name = page_file.stem
        if page_name == "HelpPage" or page_name.startswith("_"):
            continue

        keywords = PAGE_KEYWORDS.get(page_name, [page_name.lower().replace("page", "")])

        mentioned = any(kw.lower() in help_content for kw in keywords)
        if not mentioned:
            warnings.append(
                f"警告: {page_name} がヘルプページで言及されていません "
                f"(探したキーワード: {keywords})"
            )

    return warnings



def main() -> int:
    warnings = check_help_coverage()

    if warnings:
        print("ヘルプページカバレッジの問題:")
        for w in warnings:
            print(f"  {w}")
        print()
        print("HelpPage.tsx を更新して全ページの説明を追加してください。")
        return 1

    print("ヘルプページカバレッジ: OK (全ページが言及されています)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
