"""
pantheon handoff — ピア Organization 間の引き渡し（cross-org collaboration）コマンド群。

「SNS 集客 → note 販売 → アフィリ収益化」のフライホイールを結ぶ橋渡しを、人間の承認ボタンで
進める。すべての引き渡しは PolicyEngine（cross_org_handoff は必ず human_required）を通る。

  pantheon handoff create --from SNS運用 --to note販売 --kind audience_signal --title "..."
  pantheon handoff list [--to X] [--from Y] [--status pending]
  pantheon handoff approve <id>     # 承認ボタン（pending → approved）
  pantheon handoff reject  <id>     # 却下（pending → rejected）
  pantheon handoff consume <id> [--ref proposal:abc]   # 受け手が消費（approved → consumed）
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def _store(get_psm: Any):
    from core.hierarchy.org_handoff import OrgHandoffStore

    return OrgHandoffStore(platform_home=get_psm().platform_home)


def _find(store, handoff_id: str):
    """先頭一致で 1 件を解決する（完全 id でも短縮でも可）。"""
    exact = store.get(handoff_id)
    if exact:
        return exact
    matches = [h for h in store.list_handoffs() if h.handoff_id.startswith(handoff_id)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"[ERROR] ID '{handoff_id}' が複数の引き渡しに一致します。より長い ID を指定してください。")
        sys.exit(1)
    return None


async def cmd_handoff(args: argparse.Namespace, *, get_psm: Any) -> None:
    action = getattr(args, "handoff_command", None)
    store = _store(get_psm)

    if action == "create":
        payload = {}
        raw = getattr(args, "payload_json", None)
        if raw:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(f"[ERROR] --payload-json が不正な JSON です: {exc}")
                sys.exit(1)
        try:
            handoff = store.create(
                source_org=args.source,
                target_org=args.target,
                kind=args.kind,
                title=args.title,
                payload=payload,
                priority=getattr(args, "priority", "medium") or "medium",
                note=getattr(args, "note", "") or "",
            )
        except ValueError as exc:
            print(f"[ERROR] 引き渡しを作成できません: {exc}")
            sys.exit(1)
        print(f"[OK] 引き渡しを作成しました（承認待ち）: [{handoff.handoff_id}]")
        print(f"     {handoff.source_org} → {handoff.target_org}  種別: {handoff.kind}")
        print(f"     {handoff.title}")
        print(f"     ポリシー: {handoff.policy_decision}（{handoff.policy_reason}）")
        print(f"\n承認するには:  pantheon handoff approve {handoff.handoff_id}")
        return

    if action == "approve":
        handoff = _find(store, args.handoff_id)
        if not handoff:
            print(f"[ERROR] 引き渡し '{args.handoff_id}' が見つかりません。")
            sys.exit(1)
        try:
            updated = store.approve(handoff.handoff_id)
        except ValueError as exc:
            print(f"[ERROR] {exc}")
            sys.exit(1)
        print(f"[OK] 承認しました: {updated.source_org} → {updated.target_org}「{updated.title}」")
        print(f"     受け手 '{updated.target_org}' が着手できます。")
        return

    if action == "reject":
        handoff = _find(store, args.handoff_id)
        if not handoff:
            print(f"[ERROR] 引き渡し '{args.handoff_id}' が見つかりません。")
            sys.exit(1)
        try:
            store.reject(handoff.handoff_id)
        except ValueError as exc:
            print(f"[ERROR] {exc}")
            sys.exit(1)
        print(f"[OK] 却下しました:「{handoff.title}」")
        return

    if action == "consume":
        handoff = _find(store, args.handoff_id)
        if not handoff:
            print(f"[ERROR] 引き渡し '{args.handoff_id}' が見つかりません。")
            sys.exit(1)
        try:
            updated = store.mark_consumed(handoff.handoff_id, consumed_ref=getattr(args, "ref", "") or "")
        except ValueError as exc:
            print(f"[ERROR] {exc}")
            sys.exit(1)
        print(f"[OK] 消費済みにしました:「{updated.title}」 ref={updated.consumed_ref or '-'}")
        return

    # list（既定）
    handoffs = store.list_handoffs(
        source_org=getattr(args, "source", None),
        target_org=getattr(args, "target", None),
        status=getattr(args, "status", None),
    )
    if not handoffs:
        print("[INFO] 該当する引き渡しはありません。")
        return
    print(f"\n引き渡し一覧（{len(handoffs)} 件）\n")
    for h in handoffs:
        print(f"  [{h.handoff_id}]  {h.status}")
        print(f"      {h.source_org} → {h.target_org}  種別: {h.kind}  優先度: {h.priority}")
        print(f"      {h.title}")
        if h.consumed_ref:
            print(f"      消費参照: {h.consumed_ref}")
    print()


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "handoff", help="ピア Organization 間の引き渡し（集客→販売→収益化の橋渡し）"
    )
    sub = parser.add_subparsers(dest="handoff_command", required=False)

    create = sub.add_parser("create", help="引き渡しを作成する（承認待ちになる）")
    create.add_argument("--from", dest="source", required=True, help="送り手 Organization 名")
    create.add_argument("--to", dest="target", required=True, help="受け手 Organization 名")
    create.add_argument(
        "--kind",
        required=True,
        help="種別（例: audience_signal / content_brief / monetization_lead）",
    )
    create.add_argument("--title", required=True, help="引き渡しの要約")
    create.add_argument("--priority", default="medium", help="優先度（low/medium/high）")
    create.add_argument("--note", default="", help="メモ（任意）")
    create.add_argument("--payload-json", dest="payload_json", default="", help="ペイロード JSON（任意）")
    create.set_defaults(handler_name="cmd_handoff")

    approve = sub.add_parser("approve", help="承認ボタン（pending → approved）")
    approve.add_argument("handoff_id", help="引き渡し ID（先頭一致可）")
    approve.set_defaults(handler_name="cmd_handoff")

    reject = sub.add_parser("reject", help="却下（pending → rejected）")
    reject.add_argument("handoff_id", help="引き渡し ID（先頭一致可）")
    reject.set_defaults(handler_name="cmd_handoff")

    consume = sub.add_parser("consume", help="受け手が消費（approved → consumed）")
    consume.add_argument("handoff_id", help="引き渡し ID（先頭一致可）")
    consume.add_argument("--ref", default="", help="消費結果の参照（例: 生成した提案 id）")
    consume.set_defaults(handler_name="cmd_handoff")

    lst = sub.add_parser("list", help="引き渡しを一覧する")
    lst.add_argument("--from", dest="source", help="送り手で絞り込み")
    lst.add_argument("--to", dest="target", help="受け手で絞り込み")
    lst.add_argument(
        "--status", help="状態で絞り込み（pending/approved/consumed/rejected）"
    )
    lst.set_defaults(handler_name="cmd_handoff")

    # `handoff`（サブコマンド省略時）も list として扱う
    parser.add_argument("--from", dest="source", help="送り手で絞り込み（list 既定）")
    parser.add_argument("--to", dest="target", help="受け手で絞り込み（list 既定）")
    parser.add_argument("--status", help="状態で絞り込み（list 既定）")
    parser.set_defaults(handler_name="cmd_handoff")
