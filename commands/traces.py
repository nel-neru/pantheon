"""pantheon traces — 観測スパンから直近のトレースを一覧/詳細表示する（read-only）。

``~/.pantheon/spans.jsonl`` を集約する :class:`core.observability.span.TraceStore` を
使い、トレース単位のコスト/レイテンシ/品質を表示する。書き込みは一切しない。
"""

from __future__ import annotations

import argparse
import json
from typing import Any


def _print_summaries(summaries: list[dict]) -> None:
    if not summaries:
        print("（トレースがまだありません。エージェント実行後に再度お試しください。）")
        return
    print("\n=== 直近のトレース ===")
    for s in summaries:
        q = f" q={s['quality_score']}" if s.get("quality_score") is not None else ""
        cost = s.get("total_cost_usd") or 0.0
        print(
            f"  [{s['status']}] {s['trace_id']}  {s.get('name', '')}"
            f"  spans={s['span_count']}  {s.get('elapsed_ms') or 0}ms"
            f"  ${cost:.4f}  tok={s['input_tokens']}/{s['output_tokens']}{q}"
        )
    print()


def cmd_traces(args: argparse.Namespace) -> None:
    from core.observability.span import TraceStore

    store = TraceStore()
    trace_id = getattr(args, "trace_id", None)

    if trace_id:
        spans = store.get_trace(trace_id)
        if getattr(args, "json", False):
            print(json.dumps([s.to_dict() for s in spans], ensure_ascii=False, indent=2))
            return
        if not spans:
            print(f"トレースが見つかりません: {trace_id}")
            return
        print(f"\n=== トレース {trace_id} ({len(spans)} spans) ===")
        for s in spans:
            extra = f"  {s.model}" if s.model else ""
            print(f"  {s.kind:<14} {s.name:<24} {s.elapsed_ms or 0:>6}ms  [{s.status}]{extra}")
        print()
        return

    limit = getattr(args, "limit", 20) or 20
    if getattr(args, "json", False):
        print(json.dumps(store.summary(limit=limit), ensure_ascii=False, indent=2))
        return
    _print_summaries(store.recent_traces(limit=limit))


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "traces",
        help="観測スパンから直近のトレース（コスト/レイテンシ/品質）を表示する",
    )
    parser.add_argument("--limit", type=int, default=20, help="表示するトレース数（既定 20）")
    parser.add_argument("--trace-id", default=None, help="指定したトレースの span 詳細を表示する")
    parser.add_argument("--json", action="store_true", help="JSON で出力する")
    parser.set_defaults(handler_name="cmd_traces")
