from __future__ import annotations

import argparse
import asyncio
from typing import Any


def cmd_chat(args: argparse.Namespace, *, require_api_key: Any) -> None:
    """自然言語対話エージェントを起動する。"""
    from agents.chat_agent import run_chat

    require_api_key("pantheon chat")
    initial = getattr(args, "message", None)
    org = getattr(args, "org", None)
    asyncio.run(run_chat(initial_message=initial, current_org=org))


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "chat",
        help="自然言語でエージェントに依頼する（推奨）",
    )
    parser.add_argument(
        "message",
        nargs="?",
        default=None,
        help="最初のメッセージ（省略時は対話モードで起動）",
    )
    parser.add_argument(
        "--org",
        dest="org",
        default=None,
        help="操作対象の Organization 名（指定するとその org スコープで起動。"
        "省略時は org 非依存の汎用チャット）",
    )
    parser.set_defaults(handler_name="cmd_chat")
