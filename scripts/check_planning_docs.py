"""
Planning Document Hygiene checker（Phase 5 デリバラブル）。

計画段階のドキュメント（kickoff / inspiration / roadmap / WIP / フェーズ別の計画・
ロードマップ等）は **`docs/plans/`** に集約し、恒久ドキュメントフォルダ `docs/design/`
を汚さない、という規約（`docs/plans/README.md` / Group & Monetization Roadmap の
Planning Document Hygiene）を強制する。

検証内容（保守的＝誤検知を避ける）:
  - `docs/design/`（再帰）配下の .md のうち、ファイル名が計画段階を示すパターンに
    一致するものを検出し、`docs/plans/` への移動を促す。
  - 恒久的な設計ドキュメント（architecture-overview, wireframes 等）は対象外。

scripts/check_flows.py と同じスタイル（check_*() -> list[str] / main() -> int）。
PostToolUse の統合フック（.claude/hooks/post-edit-checks.mjs）と test から呼ばれる。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DESIGN_DIR = REPO_ROOT / "docs" / "design"
PLANS_DIR = REPO_ROOT / "docs" / "plans"

# ファイル名が計画/一時ドキュメントを示すパターン（大文字小文字を無視）。
_PLANNING_NAME_PATTERNS = (
    re.compile(r"kickoff", re.IGNORECASE),
    re.compile(r"inspiration", re.IGNORECASE),
    re.compile(r"roadmap", re.IGNORECASE),
    re.compile(r"(^|[-_])wip([-_]|\.)", re.IGNORECASE),
    re.compile(r"phase[-_]?\d", re.IGNORECASE),
    re.compile(r"implementation[-_]plan", re.IGNORECASE),
    re.compile(r"[-_]planning(\.|$|[-_])", re.IGNORECASE),
)

# docs/design/ に置いてよい例外ファイル名（小文字）。原則空のままにする。
_ALLOWLIST: set[str] = set()


def check_planning_docs() -> list[str]:
    errors: list[str] = []
    if not DESIGN_DIR.exists():
        return errors

    for path in sorted(DESIGN_DIR.rglob("*.md")):
        name = path.name
        if name.lower() in _ALLOWLIST:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        for pattern in _PLANNING_NAME_PATTERNS:
            if pattern.search(name):
                errors.append(
                    f"{rel}: 計画段階ドキュメントは docs/plans/ に置いてください"
                    "（docs/design/ は恒久ドキュメント専用）。"
                )
                break

    return errors


def main() -> int:
    errors = check_planning_docs()
    if errors:
        print(f"planning docs hygiene check failed ({len(errors)} issue(s)):")
        for error in errors:
            print(f"- {error}")
        print(
            "\nキックオフ/調査/ロードマップ/フェーズ計画などの一時ドキュメントは "
            "docs/plans/ に置き、完了後に恒久ドキュメント（docs/design/ 等）へ統合してください。"
        )
        return 1
    print("planning docs hygiene check passed.")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
