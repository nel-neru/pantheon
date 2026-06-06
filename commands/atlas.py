"""
pantheon atlas — リポジトリ俯瞰（Atlas）

コードベースを読み取り専用でイントロスペクションし、使用フローカタログ・
モジュール依存グラフ・CLI/API マップ・サブシステム在庫を表示/出力する。
Web の ``/api/atlas`` と同じ ``core.atlas.build_atlas`` を使う。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

_STATUS_LABEL = {
    "solid": "✓ 安定",
    "partial": "△ 一部課題",
    "fragile": "✗ 要注意",
    "unknown": "? 不明",
}


def _print_summary(atlas: dict[str, Any]) -> None:
    ov = atlas["overview"]
    print("\n=== Pantheon Repository Atlas ===")
    print(
        f"  フロー {ov['flows']} / CLI {ov['cli_commands']} / API {ov['api_routes']}"
        f"(+WS {ov['websockets']}) / ページ {ov['pages']}"
    )
    print(
        f"  サブシステム {ov['subsystems']} / モジュール {ov['modules']} / "
        f"{ov['total_files']} ファイル / {ov['total_lines']:,} 行"
    )

    print("\n--- 使用フロー（健全度） ---")
    for flow in atlas["flows"]:
        label = _STATUS_LABEL.get(flow.get("status", "unknown"), flow.get("status", "?"))
        issues = flow.get("known_issues", [])
        suffix = f"  ⚠ {len(issues)} 件の既知の問題" if issues else ""
        print(f"  [{label}] {flow['name']}{suffix}")
        trig = flow.get("trigger", {})
        if trig:
            print(f"        trigger: {trig.get('name', '')}")

    print("\n--- サブシステム在庫 ---")
    for sub in sorted(atlas["subsystems"], key=lambda s: -s["lines"]):
        print(f"  {sub['label']:<18} {sub['files']:>4} files  {sub['lines']:>7,} lines")

    high = [
        (f["name"], i)
        for f in atlas["flows"]
        for i in f.get("known_issues", [])
        if i.get("severity") == "high"
    ]
    if high:
        print(f"\n--- 高重要度の既知の問題（{len(high)} 件） ---")
        for flow_name, issue in high:
            print(f"  ✗ [{flow_name}] {issue['title']}")

    print()


def _propose_from_atlas(atlas: dict[str, Any], *, dry_run: bool) -> None:
    """Atlas の known_issues から meta 提案を生成し Meta-Improvement Org に保存する。"""
    from core.atlas import generate_atlas_proposals
    from core.bootstrap import META_ORG_NAME
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager()
    meta_org = psm.load_organization_by_name(META_ORG_NAME)
    if meta_org is None:
        print(
            "[ERROR] Meta-Improvement Organization が見つかりません。先に `pantheon init` を実行してください。"
        )
        return
    sm = psm.get_org_state_manager(meta_org)
    result = generate_atlas_proposals(atlas, sm, dry_run=dry_run)
    label = "（dry-run / 未保存）" if dry_run else ""
    print(f"\n=== Atlas → meta 改善提案 {label} ===")
    print(f"  対象 issue: {result['total']} 件")
    print(f"  新規生成 : {len(result['created'])} 件")
    print(f"  重複スキップ: {len(result['skipped'])} 件")
    for title in result["created"]:
        print(f"   + {title}")
    if not dry_run and result["created"]:
        print(f"\n  → Meta-Improvement Organization '{meta_org.name}' の改善提案に保存しました。")
        print('    `pantheon proposals --org-name "' + meta_org.name + '"` で確認できます。')


def cmd_atlas(args: argparse.Namespace) -> None:
    from core.atlas import build_atlas

    atlas = build_atlas()

    if getattr(args, "propose", False):
        _propose_from_atlas(atlas, dry_run=getattr(args, "dry_run", False))
        return

    output = getattr(args, "output", None)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(atlas, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] Atlas を書き出しました: {path}")
        return

    if getattr(args, "json", False):
        print(json.dumps(atlas, ensure_ascii=False, indent=2))
        return

    _print_summary(atlas)


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "atlas",
        help="リポジトリ俯瞰（使用フロー/依存グラフ/CLI・APIマップ）を表示・出力する",
    )
    parser.add_argument("--json", action="store_true", help="Atlas モデルを JSON で出力する")
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Atlas モデルを JSON ファイルとして書き出す（パス指定）",
    )
    parser.add_argument(
        "--propose",
        action="store_true",
        help="Atlas の known_issues から meta ImprovementProposal を生成し Meta-Improvement Org に保存する",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="--propose の生成内容を表示するだけで保存しない",
    )
    parser.set_defaults(handler_name="cmd_atlas")
