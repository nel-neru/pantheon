"""pantheon vault — Obsidian 互換ナレッジ Vault の管理（Phase 1: export / status / open / doctor）。

``~/.pantheon/vault/`` を本物の Obsidian Vault として実体化し、Pantheon のナレッジ
（insight / playbook / outcome …）を Markdown + frontmatter + ``[[wikilink]]`` で書き出す。

Phase 1 は **export のみ**（store→vault）。双方向同期（import / sync）と競合解決は Phase 2 で
配線するため、ここでは未配線の偽コマンドを出さない（実装済みに見せない）。
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

    if sub == "status":
        report = sync.status()
        print("\n=== Vault status ===")
        print(f"  Vault: {report['vault_dir']}（存在: {'はい' if report['exists'] else 'いいえ'}）")
        print(f"  ストア総件数: {report['total_entries']} / 未反映: {report['total_pending']}")
        print("\n  種別        正本   ストア  ディスク  未反映")
        for row in report["adapters"]:
            print(
                f"  {row['type']:<10} {row['canonical']:<5} "
                f"{row['store_entries']:>6} {row['on_disk']:>8} {row['pending_writes']:>7}"
            )
        if report["total_pending"]:
            print("\n  `pantheon vault export` で未反映を書き出せます。")
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
    print("使い方: pantheon vault {export|status|open|doctor}")


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "vault",
        help="Obsidian 互換ナレッジ Vault を管理する（export/status/open/doctor）",
    )
    sub = parser.add_subparsers(dest="vault_command", required=True)

    sub.add_parser(
        "export",
        help="ナレッジ（insight/playbook/outcome）を Vault へ書き出す（差分のみ・冪等）",
    )
    sub.add_parser(
        "status",
        help="ストア件数・ディスク上のノート数・未反映件数を表示する",
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
