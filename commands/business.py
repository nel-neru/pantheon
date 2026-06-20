"""`pantheon business` — 会社（Organization）の合成で「事業（Business）」を扱う CLI。

会社/能力（Organization）と事業（Business）を分離する設計（恒久原則
``docs/architecture/organization_boundaries.md``）の操作導線。合成の実体は既存のクロス Org
ハンドオフ（``core/hierarchy/org_handoff.py``）を再利用する。
"""

from __future__ import annotations

import argparse
import sys
from typing import Any


def _store():
    from core.platform.business_store import BusinessStore

    return BusinessStore()


def _parse_roles(items: list[str]) -> dict[str, str]:
    """``--role org:role`` の繰り返しを {org: role} へ。"""
    out: dict[str, str] = {}
    for raw in items or []:
        if ":" in raw:
            org, role = raw.split(":", 1)
            org, role = org.strip(), role.strip()
            if org and role:
                out[org] = role
    return out


def _parse_routes(items: list[str]) -> list[dict[str, str]]:
    """``--route from:to[:kind]`` の繰り返しを HandoffRoute dict へ。"""
    out: list[dict[str, str]] = []
    for raw in items or []:
        parts = [p.strip() for p in raw.split(":")]
        if len(parts) >= 2 and parts[0] and parts[1]:
            out.append(
                {
                    "from_org": parts[0],
                    "to_org": parts[1],
                    "kind": parts[2] if len(parts) >= 3 and parts[2] else "content_brief",
                }
            )
    return out


async def cmd_business_create(args: argparse.Namespace, *, get_psm: Any) -> None:
    """複数会社を合成した事業を作成する。"""
    from core.models.business import Business

    member_orgs = [o.strip() for o in (args.orgs or "").split(",") if o.strip()]
    business = Business(
        name=args.name,
        purpose=args.purpose or "",
        member_orgs=member_orgs,
        roles=_parse_roles(getattr(args, "role", []) or []),
        handoff_routes=_parse_routes(getattr(args, "route", []) or []),
        kpis=[k for k in (getattr(args, "kpi", []) or []) if k],
    )
    store = _store()
    if store.get(business.name):
        print(f"[WARN] Business '{business.name}' はすでに存在します")
        return
    store.save(business)
    print(f"\n[OK] Business を作成しました: {business.name}（id={business.id}）")
    print(f"  会社    : {', '.join(business.member_orgs) or '(なし)'}")
    print(f"  ルート  : {len(business.handoff_routes)} 本")
    print("  合成（保留ハンドオフ作成）: pantheon business compose " + business.name)


async def cmd_business_list(args: argparse.Namespace, *, get_psm: Any) -> None:
    businesses = _store().list_businesses()
    if not businesses:
        print("Business がありません。pantheon business create で作成してください。")
        return
    print(f"\nBusiness 一覧（{len(businesses)} 件）\n")
    for b in businesses:
        print(f"  - {b.name} [{b.status}] 会社={len(b.member_orgs)} ルート={len(b.handoff_routes)}")


async def cmd_business_show(args: argparse.Namespace, *, get_psm: Any) -> None:
    b = _store().get(args.id)
    if b is None:
        print(f"[ERROR] Business '{args.id}' が見つかりません")
        sys.exit(1)
    print(f"\nBusiness - {b.name}\n")
    print(f"  id      : {b.id}")
    print(f"  目的    : {b.purpose}")
    print(f"  状態    : {b.status}")
    print(f"  会社    : {', '.join(b.member_orgs) or '(なし)'}")
    if b.roles:
        print("  役割    : " + ", ".join(f"{o}={r}" for o, r in b.roles.items()))
    for route in b.handoff_routes:
        print(f"  ルート  : {route.from_org} → {route.to_org} ({route.kind})")
    if b.kpis:
        print("  KPI     : " + " / ".join(b.kpis))


async def cmd_business_outcomes(args: argparse.Namespace, *, get_psm: Any) -> None:
    """member 会社の成果を Business 単位で合算表示する。"""
    from core.metrics.outcomes import OutcomeStore

    b = _store().get(args.id)
    if b is None:
        print(f"[ERROR] Business '{args.id}' が見つかりません")
        sys.exit(1)
    summary = OutcomeStore().summary_for_orgs(b.member_orgs, label=b.name)
    print(f"\n成果サマリ（Business）- {b.name}（{summary.event_count} イベント）\n")
    if not summary.by_metric:
        print(
            "  記録なし。`pantheon hq outcomes record --org-name <会社> ...` で会社の成果を記録してください。"
        )
        return
    for metric, stats in sorted(summary.by_metric.items()):
        print(f"  {metric:12} 合計 {stats.get('sum', 0):.1f} / 件数 {int(stats.get('count', 0))}")
    print(f"\n  収益計: {summary.total_revenue:.0f} / リーチ計: {summary.total_reach:.0f}")


async def cmd_business_compose(args: argparse.Namespace, *, get_psm: Any) -> None:
    """handoff_routes から保留中のクロス Org ハンドオフを作成する（合成の実体化）。"""
    store = _store()
    b = store.get(args.id)
    if b is None:
        print(f"[ERROR] Business '{args.id}' が見つかりません")
        sys.exit(1)
    created = store.compose_handoffs(b)
    print(f"\n[OK] {len(created)} 件のハンドオフを作成しました（business: {b.name}）")
    for h in created:
        print(f"  - {h.source_org} → {h.target_org} ({h.kind})  [{h.handoff_id}]")
    print("承認: pantheon handoff list / handoff approve <id>")


# 状態は active / paused / archived のみ（status を実効化する・P17）。
BUSINESS_STATUSES = ("active", "paused", "archived")


async def cmd_business_update(args: argparse.Namespace, *, get_psm: Any) -> None:
    """Business を部分更新する（name/purpose/status/会社の追加削除/KPI 追加）。"""
    store = _store()
    b = store.get(args.id)
    if b is None:
        print(f"[ERROR] Business '{args.id}' が見つかりません")
        sys.exit(1)
    if args.status and args.status not in BUSINESS_STATUSES:
        print(f"[ERROR] status は {'/'.join(BUSINESS_STATUSES)} のいずれかです")
        sys.exit(1)
    if args.name and args.name != b.name:
        clash = store.get(args.name)
        if clash is not None and str(clash.id) != str(b.id):
            print(f"[ERROR] Business '{args.name}' はすでに存在します")
            sys.exit(1)
        b.name = args.name
    if args.purpose is not None:
        b.purpose = args.purpose
    if args.status:
        b.status = args.status
    for org in getattr(args, "add_org", []) or []:
        if org and org not in b.member_orgs:
            b.member_orgs.append(org)
    for org in getattr(args, "remove_org", []) or []:
        if org in b.member_orgs:
            b.member_orgs.remove(org)
    for kpi in getattr(args, "add_kpi", []) or []:
        if kpi and kpi not in b.kpis:
            b.kpis.append(kpi)
    store.save(b)
    print(f"\n[OK] Business '{b.name}' を更新しました [{b.status}]")
    print(f"  会社: {', '.join(b.member_orgs) or '(なし)'} / KPI: {len(b.kpis)}")


async def cmd_business_pause(args: argparse.Namespace, *, get_psm: Any) -> None:
    """Business を一時停止する（status=paused）。"""
    args.name = None
    args.purpose = None
    args.status = "paused"
    args.add_org = []
    args.remove_org = []
    args.add_kpi = []
    await cmd_business_update(args, get_psm=get_psm)


async def cmd_business_archive(args: argparse.Namespace, *, get_psm: Any) -> None:
    """Business をアーカイブする（status=archived）。"""
    args.name = None
    args.purpose = None
    args.status = "archived"
    args.add_org = []
    args.remove_org = []
    args.add_kpi = []
    await cmd_business_update(args, get_psm=get_psm)


async def cmd_business_from_proposal(args: argparse.Namespace, *, get_psm: Any) -> None:
    """承認済み new_business 提案を Organization+Business に組成する（フライホイール actuate）。"""
    from core.orchestration.business_application import (
        find_new_business_proposal,
        scaffold_business_from_proposal,
    )

    psm = get_psm()
    proposal = find_new_business_proposal(psm, args.org, args.id)
    if proposal is None:
        print(f"[ERROR] new_business 提案 '{args.id}' が org '{args.org}' に見つかりません")
        sys.exit(1)
    try:
        result = scaffold_business_from_proposal(proposal, psm=psm)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    org = psm.load_organization_by_name(args.org)
    if org is not None:
        psm.get_org_state_manager(org).update_proposal_status(str(proposal.get("id", "")), "done")
    print(f"\n[OK] 提案から事業を組成しました: {result['business_name']}")
    print(f"  会社    : {result['org_name']}（{'再利用' if result['reused_org'] else '新規'}）")
    print(f"  事業部  : {', '.join(result['divisions']) or '(なし)'}")
    print("  次: pantheon business compose " + result["business_name"] + " でハンドオフ実体化")


async def cmd_business_delete(args: argparse.Namespace, *, get_psm: Any) -> None:
    """Business を削除する（member 会社や成果データには触れない）。"""
    store = _store()
    b = store.get(args.id)
    if b is None:
        print(f"[ERROR] Business '{args.id}' が見つかりません")
        sys.exit(1)
    store.delete(args.id)
    print(f"\n[OK] Business '{b.name}' を削除しました（id={b.id}）")


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("business", help="会社の合成で事業（Business）を扱う")
    sub = parser.add_subparsers(dest="business_command", required=True)

    create_p = sub.add_parser("create", help="複数会社を合成した事業を作成")
    create_p.add_argument("--name", required=True)
    create_p.add_argument("--purpose", default="")
    create_p.add_argument(
        "--orgs", default="", help="会社名のカンマ区切り（例: 動画制作社,アフィリ社）"
    )
    create_p.add_argument("--role", action="append", default=[], help="org:role（繰り返し可）")
    create_p.add_argument(
        "--route",
        action="append",
        default=[],
        help="from:to[:kind]（繰り返し可、既定 kind=content_brief）",
    )
    create_p.add_argument("--kpi", action="append", default=[], help="KPI（繰り返し可）")
    create_p.set_defaults(handler_name="cmd_business_create")

    list_p = sub.add_parser("list", help="事業一覧")
    list_p.set_defaults(handler_name="cmd_business_list")

    show_p = sub.add_parser("show", help="事業詳細")
    show_p.add_argument("id", help="Business 名 または id")
    show_p.set_defaults(handler_name="cmd_business_show")

    out_p = sub.add_parser("outcomes", help="member 会社の成果を事業単位で合算")
    out_p.add_argument("id", help="Business 名 または id")
    out_p.set_defaults(handler_name="cmd_business_outcomes")

    comp_p = sub.add_parser("compose", help="ルートから保留ハンドオフを作成（合成の実体化）")
    comp_p.add_argument("id", help="Business 名 または id")
    comp_p.set_defaults(handler_name="cmd_business_compose")

    upd_p = sub.add_parser("update", help="事業を部分更新（name/purpose/status/会社/KPI）")
    upd_p.add_argument("id", help="Business 名 または id")
    upd_p.add_argument("--name", default=None, help="事業名の変更")
    upd_p.add_argument("--purpose", default=None, help="目的の変更")
    upd_p.add_argument("--status", default=None, help="状態: active/paused/archived")
    upd_p.add_argument("--add-org", dest="add_org", action="append", default=[], help="会社を追加")
    upd_p.add_argument(
        "--remove-org", dest="remove_org", action="append", default=[], help="会社を削除"
    )
    upd_p.add_argument("--add-kpi", dest="add_kpi", action="append", default=[], help="KPI を追加")
    upd_p.set_defaults(handler_name="cmd_business_update")

    pause_p = sub.add_parser("pause", help="事業を一時停止（status=paused）")
    pause_p.add_argument("id", help="Business 名 または id")
    pause_p.set_defaults(handler_name="cmd_business_pause")

    arch_p = sub.add_parser("archive", help="事業をアーカイブ（status=archived）")
    arch_p.add_argument("id", help="Business 名 または id")
    arch_p.set_defaults(handler_name="cmd_business_archive")

    del_p = sub.add_parser("delete", help="事業を削除（会社/成果データには触れない）")
    del_p.add_argument("id", help="Business 名 または id")
    del_p.set_defaults(handler_name="cmd_business_delete")

    fp = sub.add_parser(
        "from-proposal", help="承認済み new_business 提案から会社＋事業を組成（actuate）"
    )
    fp.add_argument("--org", required=True, help="提案を保持する Organization 名（例: HQ）")
    fp.add_argument("--id", required=True, help="new_business 提案 id（先頭一致可）")
    fp.set_defaults(handler_name="cmd_business_from_proposal")
