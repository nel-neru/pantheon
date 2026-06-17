"""pantheon memory — Layered Memory (Playbook) の運用コマンド。

``memory propagate`` は高有用度プレイブックを組織間で伝播する。既定は **dry-run**（提案の表示
のみ・書き込まない）。``--apply`` を付けたときだけ実際に各 target org へ追加する（冪等・人間承認
ゲート）。提案ロジックは :mod:`core.intelligence.playbook_propagation`。
"""

from __future__ import annotations

import argparse
import json
from typing import Any


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
