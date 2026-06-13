"""`pantheon trends` — 外部トレンドの収集・一覧。

`collect` で config/trend_sources.yaml の RSS/Atom を横断取得→採点→重複排除保存。
`list` で保存済みトレンドをスコア順に表示する。X/YouTube は別 collector（B-2/B-3）。
"""

from __future__ import annotations

import argparse
from typing import Any


async def cmd_trends_collect(args: argparse.Namespace) -> None:
    """RSS/Atom ソースからトレンドを収集して保存する。"""
    from core.trends.runner import collect_and_store

    result = await collect_and_store()
    print(
        f"[trends] {result['sources']} ソースから {result['collected']} 件収集、"
        f"{result['added']} 件を新規保存（重複は除外）"
    )


async def cmd_trends_list(args: argparse.Namespace) -> None:
    """保存済みトレンドをスコア順に表示する。"""
    from core.trends.store import TrendStore

    items = TrendStore().list(
        limit=args.limit,
        source=args.source,
        genre=args.genre,
        min_score=args.min_score,
    )
    if not items:
        print("[trends] 保存済みトレンドはありません（pantheon trends collect で収集）")
        return
    for i in items:
        topics = f" [{', '.join(i.topics)}]" if i.topics else ""
        print(f"  {i.score:4.1f}  ({i.source}/{i.genre or '-'}) {i.title}{topics}")
        print(f"        {i.url}")


async def cmd_trends_business_scan(args: argparse.Namespace) -> None:
    """高スコアトレンドを新規会社候補提案へ変換し承認キューへ積む（WIRE-B・自動採用しない）。"""
    from core.trends.business_pipeline import scan_business_proposals

    result = scan_business_proposals(min_score=args.min_score, max_per_run=args.max_per_run)
    if result.get("reason") == "no_org":
        print("[trends] 受け手の Organization がありません（先に org を作成してください）")
        return
    print(
        f"[trends] 新規会社候補提案を {result.get('proposals', 0)} 件起票"
        f"（走査 {result.get('scanned', 0)} 件・承認キュー /inbox で確認）"
    )


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("trends", help="外部トレンドの収集・一覧")
    sub = parser.add_subparsers(dest="trends_command", required=True)

    sp = sub.add_parser("collect", help="RSS/Atom ソースから収集・採点・保存")
    sp.set_defaults(handler_name="cmd_trends_collect")

    sp = sub.add_parser("list", help="保存済みトレンドをスコア順に表示")
    sp.add_argument("--limit", type=int, default=30, help="表示件数")
    sp.add_argument("--source", default=None, help="source で絞り込み（web/youtube/x）")
    sp.add_argument("--genre", default=None, help="ジャンルで絞り込み")
    sp.add_argument("--min-score", type=float, default=0.0, dest="min_score", help="最低スコア")
    sp.set_defaults(handler_name="cmd_trends_list")

    sp = sub.add_parser("business-scan", help="高スコアトレンド→新規会社候補提案を承認キューへ起票")
    sp.add_argument(
        "--min-score", type=float, default=7.0, dest="min_score", help="最低スコア(0..10)"
    )
    sp.add_argument(
        "--max-per-run", type=int, default=5, dest="max_per_run", help="1回の最大起票数"
    )
    sp.set_defaults(handler_name="cmd_trends_business_scan")
