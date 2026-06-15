"""core 中立性ガード — 業務固有アーティファクトが core/config/docs/content に混入していないか検査する。

恒久原則（``docs/architecture/organization_boundaries.md``）:
新規事業＝外部 Organization。業務データ/戦略/コンテンツは**兄弟リポジトリ**へ置き、
pantheon 本体の ``core/`` ``config/`` ``docs/`` ``content/`` には business を置かない。

違反があれば一覧を表示して exit 1。クリーンなら exit 0。`tests/test_core_neutrality.py` が
テストゲートでこれを強制する（再発防止の仕組み化）。新たな業務アーティファクトを禁止したくなったら
``DISALLOWED`` に追加する。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# core/config/docs/content に存在してはならない業務固有アーティファクト（過去の是正対象を含む）。
DISALLOWED = (
    "core/affiliate",
    "commands/affiliate.py",
    "config/affiliate_programs",
    "content/shortvideo_affiliate",
    "docs/plans/shortvideo-affiliate-monetization-roadmap.md",
)

# content/ 配下に置いてよい中立ファイル（業務コンテンツではないもの）。
_CONTENT_ALLOWED = {"readme.md", ".gitkeep", ".gitignore"}


def find_violations(repo: Path | None = None) -> list[str]:
    repo = repo or REPO
    violations: list[str] = []
    for rel in DISALLOWED:
        if (repo / rel).exists():
            violations.append(rel)
    # content/ 配下に per-business のコンテンツ（サブディレクトリ等）を置かない。
    content = repo / "content"
    if content.is_dir():
        for child in content.iterdir():
            if child.name.lower() in _CONTENT_ALLOWED:
                continue
            violations.append(f"content/{child.name}（業務コンテンツは外部Orgリポジトリへ）")
    return sorted(set(violations))


def main() -> int:
    violations = find_violations()
    if violations:
        print(
            "[check_core_neutrality] 業務固有アーティファクトが core/config/docs/content に存在します:"
        )
        for v in violations:
            print(f"  - {v}")
        print(
            "→ 外部 Organization の兄弟リポジトリへ移してください "
            "（docs/architecture/organization_boundaries.md の厳格ルール参照）。"
        )
        return 1
    print("[check_core_neutrality] OK: core は中立です。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
