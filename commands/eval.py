"""pantheon eval — golden タスクでエージェント/スキルを採点する。

LLM-judge（claude）で 0–10 採点し、offline（PANTHEON_NO_CLAUDE=1）では heuristic に
決定的フォールバックする。各 eval は observability の eval span を出力する。
"""

from __future__ import annotations

import argparse
import json
from typing import Any


def cmd_eval(args: argparse.Namespace) -> None:
    from core.eval.harness import run_suite
    from core.runtime.claude_code import ClaudeCodeProvider, claude_available

    suite = getattr(args, "suite", None)
    suite = None if (not suite or suite == "all") else suite
    llm = ClaudeCodeProvider() if claude_available() else None
    summary = run_suite(suite=suite, llm=llm)

    if getattr(args, "json", False):
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    print(f"\n=== Eval: {summary['suite']} ===")
    print(
        f"  {summary['passed']}/{summary['total']} passed"
        f"  (pass_rate={summary['pass_rate']}, avg_score={summary['avg_score']})"
    )
    for r in summary["results"]:
        mark = "✓" if r["passed"] else "✗"
        print(f"  {mark} [{r['task_type']}] {r['id']}  score={r['score']}  {r['feedback'][:60]}")
    print()


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "eval",
        help="golden タスクでエージェント/スキルを採点する（LLM-judge＋heuristic fallback）",
    )
    parser.add_argument(
        "--suite", default=None, help="スイート名（agents / skills / all）。既定は全件。"
    )
    parser.add_argument("--json", action="store_true", help="JSON で出力する")
    parser.set_defaults(handler_name="cmd_eval")
