"""`pantheon revenue` — 収益の自動収集（REV-COLLECT）。

`collect` で note/X/ASP アダプタを巡回し、接続済みは収益を OutcomeStore へ記録、
未接続は「接続してください」という人間タスクを承認キューへ積む（実認証は human-gate）。
"""

from __future__ import annotations

import argparse
from typing import Any


async def cmd_revenue_collect(args: argparse.Namespace) -> None:
    """外部プラットフォームから収益を自動収集する（接続済みのみ・未接続は接続タスクを起票）。"""
    from core.metrics.revenue_collectors import run_revenue_collection

    result = run_revenue_collection()
    print(
        f"[revenue] {result['recorded']} 件を記録"
        f"（収集: {', '.join(result['collected_sources']) or 'なし'}）"
    )
    if result["needs_connection"]:
        print(
            "  未接続のため接続タスクを起票: "
            + ", ".join(result["needs_connection"])
            + "（/human-tasks で確認 → 資格情報を接続すると自動収集されます）"
        )


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("revenue", help="収益の自動収集（REV-COLLECT）")
    sub = parser.add_subparsers(dest="revenue_command", required=True)

    sp = sub.add_parser("collect", help="note/X/ASP から収益を自動収集（未接続は接続タスクを起票）")
    sp.set_defaults(handler_name="cmd_revenue_collect")
