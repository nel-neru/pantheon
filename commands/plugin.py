"""`pantheon plugin` — 2階層プラグイン（会社/事業部）の一覧と事業部の追加。

会社プラグインは `pantheon org create --genre` 相当（ここでは一覧表示のみ）。
事業部プラグインは既存 Organization に Division を追加する
（`core.orchestration.division_plugins`）。
"""

from __future__ import annotations

import argparse
import sys
from typing import Any


async def cmd_plugin_list(args: argparse.Namespace, *, get_psm: Any) -> None:
    """会社プラグイン / 事業部プラグインのカタログを一覧表示する。"""
    from core.orchestration.division_plugins import load_company_plugins, load_division_plugins

    company = load_company_plugins()
    division = load_division_plugins()

    print("\n会社プラグイン（org create --genre / テンプレートのアーキタイプ）\n")
    if not company:
        print("  (なし)")
    for plugin in company:
        print(
            f"  - {plugin['id']:<20} {plugin.get('label', '')}（{plugin.get('division_count', 0)} 事業部）"
        )

    print("\n事業部プラグイン（既存 org に追加できる事業部）\n")
    if not division:
        print("  (なし)")
    for plugin in division:
        print(
            f"  - {plugin['id']:<22} [{plugin.get('category', '')}] "
            f"{plugin.get('label', '')}: {plugin.get('description', '')}"
        )
    print('\n追加: pantheon plugin add-division --org "<org名>" --plugin <id>')


async def cmd_plugin_add_division(args: argparse.Namespace, *, get_psm: Any) -> None:
    """事業部プラグインを既存 Organization に追加する。"""
    from core.bootstrap import bootstrap_platform
    from core.orchestration.division_plugins import add_division_plugin

    psm = bootstrap_platform()
    org = psm.load_organization_by_name(args.org)
    if org is None:
        print(f"[ERROR] Organization '{args.org}' が見つかりません")
        sys.exit(1)
    try:
        division = add_division_plugin(org, args.plugin)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    psm.save_organization(org)

    agents = [a.name for t in division.teams for a in t.agents]
    print(f"\n[OK] 事業部プラグイン '{args.plugin}' を '{org.name}' に追加しました\n")
    print(f"  事業部    : {division.name} [{division.type.value}]")
    print(f"  Team      : {len(division.teams)} 個 / Agent: {len(agents)} 個")
    for name in agents:
        print(f"    - {name}")
    print(f"  事業部合計: {len(org.divisions)} 個")


def register(subparsers: Any) -> None:
    plugin_parser = subparsers.add_parser("plugin", help="2階層プラグイン（会社/事業部）の管理")
    plugin_sub = plugin_parser.add_subparsers(dest="plugin_command", required=True)

    list_parser = plugin_sub.add_parser("list", help="会社/事業部プラグインのカタログを一覧表示")
    list_parser.set_defaults(handler_name="cmd_plugin_list")

    add_parser = plugin_sub.add_parser(
        "add-division", help="事業部プラグインを既存 Organization に追加する"
    )
    add_parser.add_argument("--org", required=True, help="追加先 Organization 名")
    add_parser.add_argument(
        "--plugin", required=True, help="事業部プラグイン id（pantheon plugin list で確認）"
    )
    add_parser.set_defaults(handler_name="cmd_plugin_add_division")
