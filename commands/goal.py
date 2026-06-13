from __future__ import annotations

import argparse
from typing import Any


async def cmd_goal_status(args: argparse.Namespace, *, get_platform_home: Any) -> None:
    """pantheon goal status"""
    from core.goals.goal_library import GoalLibrary

    lib = GoalLibrary(platform_home=get_platform_home())
    templates = lib._load_all()
    if not templates:
        print("ゴールの実行履歴がありません。pantheon goal run <goal_text> を試してください。")
        return
    print(f"ゴールライブラリ: {len(templates)}件")
    for template in templates[:10]:
        print(f"  [{template.goal_type}] {template.description[:50]} (使用:{template.use_count}回)")


async def cmd_goal_run(args: argparse.Namespace, *, require_api_key: Any) -> None:
    """pantheon goal run <goal_text> --workspace <org> | --new-workspace [path]"""
    from core.goals.abstract_goal_pipeline import AbstractGoalPipeline
    from core.platform.state import PlatformStateManager

    workspace = getattr(args, "workspace", None)
    new_workspace = getattr(args, "new_workspace", None)

    # 中核モデル「1 ワークスペース = 1 Organization」: 対象を明示させ、暗黙の新規 org 量産を防ぐ。
    if not workspace and new_workspace is None:
        orgs = PlatformStateManager().load_organizations()
        print("対象ワークスペースを指定してください（重複の自動生成を防ぐため必須）:")
        print("  既存を対象:   pantheon goal run <text> --workspace <Organization名>")
        print("  新規を作成:   pantheon goal run <text> --new-workspace [パス]")
        if orgs:
            print("\n登録済みワークスペース:")
            for o in orgs:
                print(f"  - {o.name}  ({o.target_repo_path or '(repo 未設定)'})")
        else:
            print("\n（まだワークスペースがありません。--new-workspace で作成できます）")
        return

    require_api_key("pantheon goal run")
    pipeline = AbstractGoalPipeline()
    result = await pipeline.run(args.goal_text, workspace=workspace, new_workspace=new_workspace)
    summary = result.summary() if callable(getattr(result, "summary", None)) else str(result)
    print(summary)


async def cmd_goal_plan(args: argparse.Namespace, *, get_platform_home: Any) -> None:
    """pantheon goal plan <target> — 月収益目標に向けた自律運用プラン（承認ゲート提案を起票）。

    決定論・LLM 非依存（claude CLI 不要）。OutcomeStore の実績から目標とのギャップを算出し、
    配分・送客・（リーチ不足なら）新規事業の打ち手を承認インボックスへ積む。--preview は起票せず表示のみ。
    """
    from core.hierarchy.portfolio_pipeline import preview_portfolio_plan, scan_portfolio_proposals

    home = get_platform_home()
    if getattr(args, "preview", False):
        result = preview_portfolio_plan(
            target=args.target, platform_home=home, source_org_name=args.source_org
        )
        gap = result["gap"]
        print(
            f"[plan] 目標 月{int(args.target)}円 / 直近 {int(gap['current'])}円 / "
            f"予測 {int(gap['forecast'])}円 / ギャップ {int(gap['present_gap'])}円"
        )
        for entry in result["plan"]:
            print(f"  - [{entry.get('kind')}] {entry.get('title')}")
        print("（--preview のため起票していません）")
        return

    result = scan_portfolio_proposals(
        target=args.target,
        platform_home=home,
        source_org_name=args.source_org,
        org_name=getattr(args, "workspace", None),
        min_reach=args.min_reach,
    )
    if result.get("reason") == "no_org":
        print("[goal] 受け手の Organization がありません（先に org を作成してください）")
        return
    print(
        f"[goal] 月{int(args.target)}円目標のプランを {result.get('proposals', 0)} 件起票"
        f"（計画 {result.get('scanned', 0)} 手・承認キュー /inbox で確認）"
    )


def register(subparsers: Any) -> None:
    goal_parser = subparsers.add_parser("goal", help="抽象ゴールの実行と履歴表示")
    goal_sub = goal_parser.add_subparsers(dest="goal_command", required=True)

    status_parser = goal_sub.add_parser("status", help="達成済みゴールの履歴を表示")
    status_parser.set_defaults(handler_name="cmd_goal_status")

    plan_parser = goal_sub.add_parser(
        "plan", help="月収益目標に向けた自律運用プランを承認ゲートで起票（claude CLI 不要）"
    )
    plan_parser.add_argument("target", type=float, help="月次収益目標額（円）")
    plan_parser.add_argument("--workspace", default=None, help="提案を積む Organization 名")
    plan_parser.add_argument("--source-org", default="HQ", dest="source_org", help="提案主体名")
    plan_parser.add_argument(
        "--min-reach",
        type=float,
        default=0.0,
        dest="min_reach",
        help="新規事業提案を促すリーチ下限",
    )
    plan_parser.add_argument("--preview", action="store_true", help="起票せずプランを表示のみ")
    plan_parser.set_defaults(handler_name="cmd_goal_plan")

    run_parser = goal_sub.add_parser("run", help="抽象ゴールを自律実行する（claude CLI が必要）")
    run_parser.add_argument("goal_text", help="実行するゴール文（例: 'ECサイトを作りたい'）")
    run_parser.add_argument(
        "--workspace",
        default=None,
        help="既存ワークスペース（Organization 名）を対象に実行する",
    )
    run_parser.add_argument(
        "--new-workspace",
        nargs="?",
        const=True,
        default=None,
        metavar="PATH",
        help="新規ワークスペースを作成して実行（パス省略時は既定の場所に作成）",
    )
    run_parser.set_defaults(handler_name="cmd_goal_run")
