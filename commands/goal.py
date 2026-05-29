from __future__ import annotations

import argparse
from typing import Any


async def cmd_goal_status(args: argparse.Namespace, *, get_platform_home: Any) -> None:
    """repocorp goal status"""
    from core.goals.goal_library import GoalLibrary

    lib = GoalLibrary(platform_home=get_platform_home())
    templates = lib._load_all()
    if not templates:
        print("ゴールの実行履歴がありません。repocorp goal run <goal_text> を試してください。")
        return
    print(f"ゴールライブラリ: {len(templates)}件")
    for template in templates[:10]:
        print(f"  [{template.goal_type}] {template.description[:50]} (使用:{template.use_count}回)")


async def cmd_goal_run(args: argparse.Namespace, *, require_api_key: Any) -> None:
    """repocorp goal run <goal_text>"""
    from core.goals.abstract_goal_pipeline import AbstractGoalPipeline

    require_api_key("repocorp goal run")
    pipeline = AbstractGoalPipeline()
    result = await pipeline.run(args.goal_text)
    summary = result.summary() if callable(getattr(result, "summary", None)) else str(result)
    print(summary)


def register(subparsers: Any) -> None:
    goal_parser = subparsers.add_parser("goal", help="抽象ゴールの実行と履歴表示")
    goal_sub = goal_parser.add_subparsers(dest="goal_command", required=True)

    status_parser = goal_sub.add_parser("status", help="達成済みゴールの履歴を表示")
    status_parser.set_defaults(handler_name="cmd_goal_status")

    run_parser = goal_sub.add_parser("run", help="抽象ゴールを自律実行する（ANTHROPIC_API_KEY が必要）")
    run_parser.add_argument("goal_text", help="実行するゴール文（例: 'ECサイトを作りたい'）")
    run_parser.set_defaults(handler_name="cmd_goal_run")
