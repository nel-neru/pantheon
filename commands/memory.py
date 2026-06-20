"""pantheon memory — Layered Memory (Playbook) の運用コマンド。

``memory propagate`` は高有用度プレイブックを組織間で伝播する。既定は **dry-run**（提案の表示
のみ・書き込まない）。``--apply`` を付けたときだけ実際に各 target org へ追加する（冪等・人間承認
ゲート）。提案ロジックは :mod:`core.intelligence.playbook_propagation`。
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def cmd_memory_list(args: argparse.Namespace) -> None:
    """Playbook（過去の学び）を有用度順に一覧する（GUI /api/memory/playbook と同等）。"""
    from core.intelligence.memory_bank import MemoryBank
    from core.platform.state import get_platform_home

    bank = MemoryBank(get_platform_home())
    entries = bank.recall(
        category=getattr(args, "category", None) or None,
        limit=max(1, getattr(args, "limit", 10)),
    )
    if not entries:
        print("Playbook はまだありません（pantheon memory capture で追加できます）。")
        return
    print(f"\nPlaybook（上位 {len(entries)} 件）\n")
    for e in entries:
        print(
            f"  - [{e.category}] {e.title}"
            f"（有用度 {e.usefulness_score:.1f}・使用 {e.usage_count} 回）"
        )
        if getattr(args, "verbose", False):
            print(f"      {e.content.strip()[:200]}")


def cmd_memory_capture(args: argparse.Namespace) -> None:
    """施策ノート（学び）を Playbook に追加する（冪等・GUI の capture と同等）。"""
    from core.intelligence.memory_bank import MemoryBank
    from core.platform.state import get_platform_home

    title = (getattr(args, "title", "") or "").strip()
    if not title:
        print("[ERROR] --title は必須です")
        sys.exit(1)
    entry = MemoryBank(get_platform_home()).capture(
        title,
        getattr(args, "content", "") or "",
        category=getattr(args, "category", "general") or "general",
        org_name=getattr(args, "org_name", "") or "",
    )
    print(f"[OK] Playbook に追加しました: [{entry.category}] {entry.title}")


def cmd_memory_propagate(args: argparse.Namespace) -> None:
    from core.intelligence.playbook_propagation import apply_propagations, propose_propagations

    candidates = propose_propagations(
        min_usefulness=getattr(args, "min_usefulness", 1.0),
        top_per_org=getattr(args, "top_per_org", 5),
    )
    do_apply = bool(getattr(args, "apply", False))
    applied = apply_propagations(candidates) if do_apply else 0

    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "mode": "apply" if do_apply else "dry-run",
                    "candidate_count": len(candidates),
                    "applied": applied,
                    "candidates": [c.to_dict() for c in candidates],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    mode = "APPLY" if do_apply else "dry-run"
    print(f"\n=== Playbook 組織横断伝播 ({mode}) ===")
    print(f"  候補: {len(candidates)} 件")
    for c in candidates:
        print(
            f"  - [{c.category}] {c.title}  {c.source_org} → {c.target_org}"
            f"  (有用度 {c.usefulness_score:.1f})"
        )
    if do_apply:
        print(f"\n  適用: {applied} 件を各 target org に追加しました（冪等）。")
    else:
        print("\n  （dry-run。実際に追加するには --apply を付けてください＝人間承認ゲート）")
    print()


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("memory", help="Layered Memory (Playbook) の運用")
    sub = parser.add_subparsers(dest="memory_command", required=True)

    lst = sub.add_parser("list", help="Playbook を有用度順に一覧（GUI と同等）")
    lst.add_argument("--category", default=None, help="カテゴリで絞り込み")
    lst.add_argument("--limit", type=int, default=10, help="表示件数（既定 10）")
    lst.add_argument("--verbose", action="store_true", help="本文も表示する")
    lst.set_defaults(handler_name="cmd_memory_list")

    cap = sub.add_parser("capture", help="施策ノート（学び）を Playbook に追加（冪等）")
    cap.add_argument("--title", required=True, help="タイトル（必須）")
    cap.add_argument("--content", default="", help="本文")
    cap.add_argument("--category", default="general", help="カテゴリ（既定 general）")
    cap.add_argument("--org-name", dest="org_name", default="", help="由来 Organization 名")
    cap.set_defaults(handler_name="cmd_memory_capture")

    prop = sub.add_parser(
        "propagate",
        help="高有用度プレイブックを組織間で伝播する（既定 dry-run／--apply で書込）",
    )
    prop.add_argument(
        "--apply",
        action="store_true",
        help="実際に各 target org へ追加する（既定は dry-run・人間承認ゲート）",
    )
    prop.add_argument(
        "--min-usefulness",
        type=float,
        default=1.0,
        help="伝播対象とする最小 usefulness（既定 1.0）",
    )
    prop.add_argument(
        "--top-per-org", type=int, default=5, help="各 org から伝播する上位件数（既定 5）"
    )
    prop.add_argument("--json", action="store_true", help="JSON で出力する")
    prop.set_defaults(handler_name="cmd_memory_propagate")
