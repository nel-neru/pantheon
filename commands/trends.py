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
