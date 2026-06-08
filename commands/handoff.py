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
    """先頭一致で 1 件を解決する（完全 id でも、`handoff:` を省いた短縮 uuid でも可）。"""
    exact = store.get(handoff_id)
    if exact:
        return exact

    def _matches(full_id: str) -> bool:
        # "handoff:<uuid>" に対し、フル一致／フル接頭辞／uuid 部分の接頭辞 のいずれでも可。
        uuid_part = full_id.split(":", 1)[1] if ":" in full_id else full_id
        return full_id.startswith(handoff_id) or uuid_part.startswith(handoff_id)

    matches = [h for h in store.list_handoffs() if _matches(h.handoff_id)]
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

        # 承認 → 受け手 org に提案を自動生成。
        #   既定: content_asset ブリーフ（決定論・即時）。
        #   --draft: 本文ドラフト（claude 生成・数秒。承認1ボタンで本文まで）。
        want_draft = bool(getattr(args, "draft", False))
        if want_draft:
            from core.hierarchy.org_handoff import draft_handoff

            proposal = await draft_handoff(updated, psm=get_psm())
            kind_label = "本文ドラフト"
        else:
            from core.hierarchy.org_handoff import materialize_handoff

            proposal = materialize_handoff(updated, psm=get_psm())
            kind_label = "ブリーフ"
        if proposal is None:
            print(
                f"     受け手 '{updated.target_org}' が着手できます"
                "（自動生成は対象 org 未登録/repo 未設定のためスキップ）。"
            )
            return
        store.record_materialization(updated.handoff_id, str(proposal.id))
        print(f"     受け手 '{updated.target_org}' に{kind_label}提案を自動生成しました:")
        print(f"       [{str(proposal.id)[:8]}] {proposal.title}")
        print(
            f'     適用するには:  pantheon proposal apply {str(proposal.id)[:8]} '
            f'--org-name "{updated.target_org}"'
        )
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

    if action == "draft":
        handoff = _find(store, args.handoff_id)
        if not handoff:
            print(f"[ERROR] 引き渡し '{args.handoff_id}' が見つかりません。")
            sys.exit(1)
        from core.hierarchy.org_handoff import draft_handoff

        proposal = await draft_handoff(handoff, psm=get_psm())
        if proposal is None:
            print(f"[ERROR] 受け手 '{handoff.target_org}' が未登録/repo 未設定のため本文生成できません。")
            sys.exit(1)
        print(f"[OK] 本文ドラフトを生成しました（受け手 '{handoff.target_org}'）:")
        print(f"       [{str(proposal.id)[:8]}] {proposal.title}")
        print(
            f'     適用するには:  pantheon proposal apply {str(proposal.id)[:8]} '
            f'--org-name "{handoff.target_org}"'
        )
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
    approve.add_argument(
        "--draft",
        action="store_true",
        help="承認と同時に本文ドラフトまで生成する（claude 経由。1ボタンで本文まで）",
    )
    approve.set_defaults(handler_name="cmd_handoff")

    reject = sub.add_parser("reject", help="却下（pending → rejected）")
    reject.add_argument("handoff_id", help="引き渡し ID（先頭一致可）")
    reject.set_defaults(handler_name="cmd_handoff")

    draft = sub.add_parser("draft", help="本文ドラフトを生成（claude 経由、不在時は決定論テンプレ）")
    draft.add_argument("handoff_id", help="引き渡し ID（先頭一致可）")
    draft.set_defaults(handler_name="cmd_handoff")

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
