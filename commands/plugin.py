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
    """会社プラグイン（install できる manifest）/ 事業部プラグインのカタログを一覧表示する。"""
    from core.orchestration.company_plugins import load_company_plugin_manifests
    from core.orchestration.division_plugins import (
        load_company_archetypes,
        load_division_plugins,
    )

    manifests = load_company_plugin_manifests()
    archetypes = load_company_archetypes()
    division = load_division_plugins()

    # 会社プラグイン = install-company で「丸ごと起動できる」manifest（list と install を一致させる）。
    print("\n会社プラグイン（install-company で丸ごと起動できる）\n")
    if not manifests:
        print("  (なし)")
    for m in manifests:
        divisions = ", ".join(str(d) for d in (m.get("divisions") or []))
        print(f"  - {m['id']:<20} {m.get('label', '')} [{m.get('genre', '')}]")
        if divisions:
            print(f"      事業部: {divisions}")
    if manifests:
        print('\n  起動: pantheon plugin install-company --id <id> [--name "会社名"]')

    # アーキタイプは org create --genre 用の参考（install はできない）。混同させない。
    if archetypes:
        print("\n会社アーキタイプ（参考・org create --genre 用 / install 不可）\n")
        for a in archetypes:
            print(f"  - {a['id']:<20} {a.get('label', '')}（{a.get('division_count', 0)} 事業部）")

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


async def cmd_plugin_install_company(args: argparse.Namespace, *, get_psm: Any) -> None:
    """会社プラグイン manifest から Organization を起動する（GUI の install と同等の CLI 経路）。"""
    from core.bootstrap import bootstrap_platform
    from core.orchestration.company_plugins import install_company_plugin

    psm = bootstrap_platform()
    try:
        result = install_company_plugin(
            args.id, psm=psm, name=args.name or None, repo_path=args.repo or None
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    print(f"\n[OK] 会社プラグイン '{args.id}' を起動しました: {result['org_name']}\n")
    print(f"  事業部  : {', '.join(result['divisions'])}")
    print(f"  Agent   : {result['agent_count']} / 人間タスク: {result['human_tasks_created']}")
    print(f"  分離     : external / 管理: {result['management_mode']}")
    print(f"  ワークスペース: {result['workspace_path']}")
    print(f'\n次のステップ: pantheon business create --orgs "{result["org_name"]},..." で合成')


async def cmd_plugin_scaffold_division(args: argparse.Namespace, *, get_psm: Any) -> None:
    """テンプレから事業部プラグインの雛形を生成する（表示、または --write でカタログ追記）。"""
    import yaml

    from core.orchestration.division_plugins import get_division_plugin
    from core.orchestration.plugin_templates import scaffold_division_plugin
    from core.paths import resource_path

    entry = scaffold_division_plugin(
        args.id,
        args.label,
        args.category,
        description=args.description or "",
        mission=args.mission or "",
    )
    print(f"\n[scaffold] 事業部プラグイン '{entry['id']}' [{entry['category']}]")
    print(f"  事業部 : {entry['department']['name']} ({entry['department']['type']})")
    print(f"  Team   : {len(entry['department']['teams'])} 個")
    for team in entry["department"]["teams"]:
        print(f"    - {team['name']}: {', '.join(team['required_skills'])}")

    if not args.write:
        # 既定はテンプレ形（id/label/category/description）を表示する。ローダがこれを展開する。
        compact = {
            "id": entry["id"],
            "label": entry["label"],
            "category": entry["category"],
            "description": entry["description"],
        }
        print("\n--- カタログへ追加するテンプレ形エントリ（--write で自動追記）---\n")
        print(yaml.safe_dump([compact], allow_unicode=True, sort_keys=False))
        return

    if get_division_plugin(entry["id"]) is not None:
        print(f"\n[INFO] id '{entry['id']}' は既にカタログに存在します（追記しません）。")
        return

    path = resource_path("config", "division_plugins.yaml")
    block = (
        f"\n  - id: {entry['id']}\n"
        f"    label: {entry['label']}\n"
        f"    category: {entry['category']}\n"
        f"    description: {entry['description']}\n"
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(block)
    print(f"\n[OK] '{entry['id']}' を {path.name} に追記しました（pantheon plugin list で確認）。")


async def cmd_plugin_scaffold_company(args: argparse.Namespace, *, get_psm: Any) -> None:
    """テンプレから会社プラグイン manifest の雛形を生成する（表示、または --write でカタログ追記）。

    scaffold-division の会社版。divisions 未指定なら --category のプリセット（default_divisions）
    から既定の事業部名を与える。--write で config/company_plugins.yaml に追記し、以後
    `pantheon plugin install-company --id <id>` で丸ごと起動できる（list==install）。
    """
    import yaml

    from core.orchestration.company_plugins import get_company_plugin_manifest
    from core.orchestration.plugin_templates import scaffold_company_plugin
    from core.paths import resource_path

    manifest = scaffold_company_plugin(
        args.id,
        args.label,
        args.genre,
        divisions=list(args.division or []) or None,
        category=args.category or None,
        initial_kpis=list(args.kpi or []),
        human_tasks=list(getattr(args, "human_task", []) or []),
        weekly_review=args.weekly_review or "",
    )
    print(f"\n[scaffold] 会社プラグイン '{manifest['id']}' [{manifest.get('genre', '')}]")
    print(f"  事業部 : {', '.join(manifest['divisions'])}")
    print(f"  初期KPI: {', '.join(manifest['initial_kpis']) or '(なし)'}")

    if not args.write:
        print("\n--- カタログへ追加する manifest（--write で自動追記）---\n")
        print(yaml.safe_dump([manifest], allow_unicode=True, sort_keys=False))
        return

    if get_company_plugin_manifest(manifest["id"]) is not None:
        print(f"\n[INFO] id '{manifest['id']}' は既にカタログに存在します（追記しません）。")
        return

    path = resource_path("config", "company_plugins.yaml")
    dumped = yaml.safe_dump([manifest], allow_unicode=True, sort_keys=False)
    # `plugins:` リストの要素として 2 スペース字下げして追記する（空行はそのまま）。
    indented = "".join(
        ("  " + line if line.strip() else line) for line in dumped.splitlines(keepends=True)
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n" + indented)
    print(
        f"\n[OK] '{manifest['id']}' を {path.name} に追記しました"
        f"（pantheon plugin install-company --id {manifest['id']} で起動）。"
    )


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

    install_company_parser = plugin_sub.add_parser(
        "install-company",
        help="会社プラグインから Organization を起動する（GUI の install と同等）",
    )
    install_company_parser.add_argument(
        "--id", required=True, help="会社プラグイン id（pantheon plugin list で確認）"
    )
    install_company_parser.add_argument(
        "--name", default="", help="Organization 名の上書き（省略可）"
    )
    install_company_parser.add_argument(
        "--repo", default="", help="ワークスペースのパス（省略時は ~/.pantheon/workspaces 配下）"
    )
    install_company_parser.set_defaults(handler_name="cmd_plugin_install_company")

    scaffold_parser = plugin_sub.add_parser(
        "scaffold-division",
        help="テンプレから事業部プラグインの雛形を生成（--write でカタログ追記）",
    )
    scaffold_parser.add_argument("--id", required=True, help="プラグイン id（一意）")
    scaffold_parser.add_argument("--label", required=True, help="表示名（事業部名）")
    scaffold_parser.add_argument(
        "--category",
        required=True,
        help="カテゴリ: audience/monetization/full_funnel/operations/content",
    )
    scaffold_parser.add_argument("--description", default="", help="説明（省略可）")
    scaffold_parser.add_argument("--mission", default="", help="事業部ミッション（省略可）")
    scaffold_parser.add_argument(
        "--write", action="store_true", help="division_plugins.yaml にテンプレ形で追記する"
    )
    scaffold_parser.set_defaults(handler_name="cmd_plugin_scaffold_division")

    scaffold_company_parser = plugin_sub.add_parser(
        "scaffold-company",
        help="テンプレから会社プラグイン manifest の雛形を生成（--write でカタログ追記）",
    )
    scaffold_company_parser.add_argument("--id", required=True, help="会社プラグイン id（一意）")
    scaffold_company_parser.add_argument("--label", required=True, help="表示名（会社名）")
    scaffold_company_parser.add_argument(
        "--genre", required=True, help="ジャンル（例: digital_content / affiliate_marketing）"
    )
    scaffold_company_parser.add_argument(
        "--category",
        default="",
        help="divisions 未指定時の既定構成: audience/monetization/full_funnel/operations/content",
    )
    scaffold_company_parser.add_argument(
        "--division", action="append", default=[], help="事業部名（繰り返し可・省略時はプリセット）"
    )
    scaffold_company_parser.add_argument(
        "--kpi", action="append", default=[], help="初期KPI（繰り返し可）"
    )
    scaffold_company_parser.add_argument(
        "--human-task",
        dest="human_task",
        action="append",
        default=[],
        help="人間タスク（繰り返し可）",
    )
    scaffold_company_parser.add_argument(
        "--weekly-review", default="", help="週次レビュー方針（省略可）"
    )
    scaffold_company_parser.add_argument(
        "--write", action="store_true", help="company_plugins.yaml に manifest を追記する"
    )
    scaffold_company_parser.set_defaults(handler_name="cmd_plugin_scaffold_company")
