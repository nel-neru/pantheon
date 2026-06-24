"""pantheon vault — Obsidian 互換ナレッジ Vault の管理（export/sync/import/status/open/doctor）。

``~/.pantheon/vault/`` を本物の Obsidian Vault として実体化し、Pantheon のナレッジを
Markdown + frontmatter + ``[[wikilink]]`` で双方向同期する。

- ``export`` = store→vault（ストア勝ち・一方向・冪等）
- ``import`` = vault→store（Obsidian の編集を書き戻す・3-way 競合判定）
- ``sync``   = import→export（双方向 1 往復）
"""

from __future__ import annotations

import argparse
from typing import Any


def cmd_vault(args: argparse.Namespace) -> None:
    from core.platform.state import get_platform_home
    from core.vault import build_default_sync, get_vault_dir

    sub = getattr(args, "vault_command", None)
    home = get_platform_home()
    vault_dir = get_vault_dir(home)

    if sub == "open":
        print(str(vault_dir))
        if not vault_dir.exists():
            print("（まだ存在しません。`pantheon vault export` で生成してください）")
        else:
            # Obsidian アプリで開くための URI（手動でクリック/貼り付け用・自動起動はしない）。
            print(f"obsidian://open?path={vault_dir}")
        return

    sync = build_default_sync(home)

    if sub == "export":
        stats = sync.export()
        print("\n=== Vault export 完了 ===")
        print(f"  書き込み: {stats.written} 件 / スキップ(変更なし): {stats.skipped} 件")
        if stats.by_type:
            for ptype, count in sorted(stats.by_type.items()):
                print(f"    - {ptype}: {count}")
        print(f"  Vault: {vault_dir}")
        print("  → 本物の Obsidian でこのフォルダを開くと閲覧できます。")
        return

    if sub == "sync":
        result = sync.sync()
        imp, exp = result["import"], result["export"]
        print("\n=== Vault sync（双方向）完了 ===")
        print(
            f"  取り込み(import): {imp['imported']} 件 / 競合: {imp['conflicts']} 件 / "
            f"reject: {imp['rejected']} 件 / orphan: {imp['orphan']} 件"
        )
        print(f"  書き出し(export): {exp['written']} 件 / スキップ: {exp['skipped']} 件")
        if imp["conflict_paths"]:
            print("  ⚠ 競合（.conflict.md に両版を保全。整えて削除→再 sync）:")
            for p in imp["conflict_paths"]:
                print(f"    - {p}")
        print(f"  Vault: {vault_dir}")
        return

    if sub == "import":
        result = sync.import_vault()
        print("\n=== Vault import（vault→store）完了 ===")
        print(
            f"  取り込み: {result.imported} 件 / 競合: {result.conflicts} 件 / "
            f"reject: {result.rejected} 件 / orphan: {result.orphan} 件 / "
            f"スキップ: {result.skipped} 件"
        )
        for p in result.conflict_paths:
            print(f"    ⚠ 競合: {p}")
        return

    if sub == "status":
        report = sync.status()
        print("\n=== Vault status ===")
        print(f"  Vault: {report['vault_dir']}（存在: {'はい' if report['exists'] else 'いいえ'}）")
        print(f"  ストア総件数: {report['total_entries']} / 未反映: {report['total_pending']}")
        if report.get("conflict_count"):
            print(f"  ⚠ 競合: {report['conflict_count']} 件（.conflict.md を解決してください）")
        print("\n  種別        正本   ストア  ディスク  未反映")
        for row in report["adapters"]:
            print(
                f"  {row['type']:<10} {row['canonical']:<5} "
                f"{row['store_entries']:>6} {row['on_disk']:>8} {row['pending_writes']:>7}"
            )
        if report["total_pending"]:
            print("\n  `pantheon vault export` で未反映を書き出せます。")
        return

    if sub == "graph":
        import json

        from core.vault import build_vault_graph, to_dot

        graph = build_vault_graph(vault_dir)
        fmt = getattr(args, "format", "json")
        if fmt == "dot":
            print(to_dot(graph))
        else:
            print(json.dumps(graph, ensure_ascii=False, indent=2, default=str))
        return

    if sub == "doctor":
        report = sync.doctor()
        print("\n=== Vault doctor ===")
        print(f"  検査(管理ノート): {report['checked']} 件 / 対象外: {report['unmanaged']} 件")
        if report["ok"]:
            print("  ✓ 問題は見つかりませんでした。")
        else:
            print(f"  ✗ {len(report['issues'])} 件の問題:")
            for issue in report["issues"]:
                print(f"    - {issue['path']}: {issue['problem']}")
        return

    # サブコマンド未指定（required=True なので通常到達しない）。
    print("使い方: pantheon vault {export|sync|import|status|graph|open|doctor}")


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "vault",
        help="Obsidian 互換ナレッジ Vault を管理する（export/sync/import/status/open/doctor）",
    )
    sub = parser.add_subparsers(dest="vault_command", required=True)

    sub.add_parser(
        "export",
        help="ナレッジを Vault へ書き出す（store→vault・差分のみ・冪等）",
    )
    sub.add_parser(
        "sync",
        help="双方向同期する（Obsidian の編集を取り込み→最新を書き出し）",
    )
    sub.add_parser(
        "import",
        help="Obsidian の編集を store へ書き戻す（vault→store・3-way 競合判定）",
    )
    sub.add_parser(
        "status",
        help="ストア件数・ディスク上のノート数・未反映件数・競合を表示する",
    )
    graph_parser = sub.add_parser(
        "graph",
        help="Vault のノード/エッジグラフを出力する（GUI/Graphviz 用）",
    )
    graph_parser.add_argument(
        "--format",
        choices=["json", "dot"],
        default="json",
        help="出力形式（json=ノード/エッジ、dot=Graphviz）",
    )
    sub.add_parser(
        "open",
        help="Vault のパス（と Obsidian で開く URI）を表示する",
    )
    sub.add_parser(
        "doctor",
        help="Vault 内ノートの frontmatter を検証する（読み取り専用）",
    )

    parser.set_defaults(handler_name="cmd_vault")
