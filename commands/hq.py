"""
pantheon hq — 本社（Meta-Improvement Organization / HQ）による子 Organization の
診断・構造介入提案・適用コマンド群（Phase 5）。

  pantheon hq diagnose                 # 全子 Organization を診断
  pantheon hq propose [--dry-run]      # 弱みから構造介入提案を生成・保存
  pantheon hq apply <id> --org-name X  # 承認済み相当の構造介入を Policy+PreTask 経由で適用

すべての適用は PolicyEngine（cross-org 介入は必ず human_required）を通り、
PreTaskOrchestrator 経由で構造介入 executor に委任される（no-bypass 不変条件）。
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from core.models.organization import is_structural_intervention_dict


def _parse_outcomes_file(path) -> list[dict[str, Any]]:
    """成果イベントの取り込みファイル（.json または .csv）を行 dict の列に解析する。

    JSON: オブジェクトの配列、または ``{"rows": [...]}``。
    CSV: ヘッダ行（org_name,metric,value[,unit,source,note,occurred_at]）付き。BOM 許容。
    """
    text = path.read_text(encoding="utf-8-sig")
    if str(path).lower().endswith(".json"):
        import json

        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("rows", [])
        return [dict(row) for row in data if isinstance(row, dict)]
    # CSV
    import csv
    import io

    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def _find_pending_proposal(
    proposals: list[dict[str, Any]], proposal_id: str
) -> dict[str, Any] | None:
    return next(
        (p for p in proposals if str(p.get("id", "")).startswith(proposal_id)),
        None,
    )


async def cmd_hq_diagnose(args: argparse.Namespace, *, get_psm: Any) -> None:
    from core.hierarchy.hq_interventions import HQInterventionProposer

    proposer = HQInterventionProposer(get_psm())
    targets = proposer.list_target_orgs()
    if not targets:
        print("[INFO] 診断対象の子 Organization がありません（system/HQ のみ）。")
        return
    for org in targets:
        report = proposer.diagnose_org(org)
        print(proposer._diag.format_report(report))
        print()


async def cmd_hq_propose(args: argparse.Namespace, *, get_psm: Any) -> None:
    from core.hierarchy.hq_interventions import HQInterventionProposer

    dry_run = bool(getattr(args, "dry_run", False))
    proposer = HQInterventionProposer(get_psm())
    proposals = proposer.propose_all(persist=not dry_run, dry_run=dry_run)
    if not proposals:
        print("[INFO] 新規の構造介入提案はありません（既存提案と重複/弱みなし）。")
        return
    verb = "生成（dry-run・未保存）" if dry_run else "生成・保存"
    print(f"[OK] 構造介入提案を {len(proposals)} 件 {verb}しました:\n")
    for proposal in proposals:
        print(f"  - [{str(proposal.id)[:8]}] {proposal.title}")
        print(f"      対象: {proposal.target_org_name}  種別: {proposal.intervention_type}")
        print(f"      {str(proposal.description)[:90]}")
        print()
    if not dry_run:
        print("適用するには:  pantheon hq apply <id> --org-name <対象Org名>")


async def cmd_hq_apply(
    args: argparse.Namespace,
    *,
    confirm_action: Any,
    get_psm: Any,
    require_api_key: Any,
) -> None:
    from core.orchestration.structural_intervention import execute_structural_intervention
    from core.policy.engine import ApprovalDecision, PolicyEngine

    # 構造介入は決定論的（claude CLI 不要）。require_api_key は要求しない（Web 経路と一致）。
    psm = get_psm()
    org = psm.load_organization_by_name(args.org_name)
    if not org:
        print(f"[ERROR] Organization '{args.org_name}' が見つかりません。")
        sys.exit(1)

    sm = psm.get_org_state_manager(org)
    proposal = _find_pending_proposal(
        sm.get_pending_improvement_proposals(limit=200), args.proposal_id
    )
    if not proposal:
        print(f"[ERROR] ID '{args.proposal_id}' に一致する未対応提案が見つかりません。")
        sys.exit(1)

    if not is_structural_intervention_dict(proposal):
        print(
            "[ERROR] この提案は構造介入ではありません。通常の適用は `pantheon proposal apply` を使ってください。"
        )
        sys.exit(1)

    # cross-org 介入も必ず PolicyEngine を通す（human_required になる）。
    policy_path = psm.platform_home / "policy.yaml"
    verdict = PolicyEngine(policy_path if policy_path.exists() else None).evaluate(proposal)
    sm.update_proposal_fields(
        str(proposal.get("id", "")),
        policy_decision=verdict.decision.value,
        policy_reason=verdict.reason,
        policy_rule=verdict.rule_name,
    )
    if verdict.decision == ApprovalDecision.REJECT:
        print(f"[ERROR] ポリシーにより承認できません: {verdict.reason}")
        sm.update_proposal_status(str(proposal.get("id", "")), "rejected")
        sys.exit(1)

    print(f"\n構造介入を適用します: {proposal.get('title')}")
    print(f"   対象 Org : {proposal.get('target_org_name')}")
    print(f"   種別     : {proposal.get('intervention_type')}")
    print(f"   ポリシー : {verdict.decision.value}（{verdict.reason}）\n")

    if not confirm_action(
        f"提案 '{proposal.get('title')}' を適用しますか?",
        assume_yes=getattr(args, "yes", False),
    ):
        print("[INFO] 適用を中止しました。")
        return

    sm.update_proposal_status(str(proposal.get("id", "")), "in_progress")
    result = await execute_structural_intervention(proposal, psm=psm)
    if not result.success:
        print(f"[ERROR] 適用失敗: {result.error}")
        sm.update_proposal_status(str(proposal.get("id", "")), "failed")
        sys.exit(1)

    sm.update_proposal_status(str(proposal.get("id", "")), "done")
    print(f"[OK] 構造介入を適用しました: {result.output}")


async def cmd_hq_outcomes(args: argparse.Namespace, *, get_psm: Any) -> None:
    """成果イベントを記録/一覧する（Phase 8: 経済フィードバック）。"""
    from core.metrics.outcomes import OutcomeStore

    psm = get_psm()
    store = OutcomeStore(platform_home=psm.platform_home)
    action = getattr(args, "outcomes_action", None)

    if action == "record":
        event = store.record(
            args.org_name,
            args.metric,
            args.value,
            unit=getattr(args, "unit", "") or "",
            source=getattr(args, "source", "") or "",
            note=getattr(args, "note", "") or "",
        )
        print(
            f"[OK] 成果を記録しました: {event.org_name} {event.metric}={event.value} {event.unit}"
        )
        return

    if action == "import":
        from pathlib import Path

        path = Path(args.path)
        if not path.exists():
            print(f"[ERROR] ファイルが見つかりません: {path}")
            sys.exit(1)
        try:
            rows = _parse_outcomes_file(path)
        except (ValueError, OSError) as exc:
            print(f"[ERROR] ファイルを解析できません: {exc}")
            sys.exit(1)
        added, skipped = store.record_many(rows, default_org=getattr(args, "org_name", "") or "")
        print(f"[OK] 成果を {len(added)} 件取り込みました（スキップ {skipped} 件）。")
        orgs = sorted({e.org_name for e in added})
        for org in orgs:
            summary = store.summary_for_org(org)
            print(
                f"  {org}: リーチ計 {summary.total_reach:.0f} / 収益計 {summary.total_revenue:.0f}"
            )
        return

    if action == "export":
        csv_text = store.export_events_csv(
            getattr(args, "org_name", None) or None,
            metric=getattr(args, "metric", None) or None,
            start_date=getattr(args, "start_date", None) or None,
            end_date=getattr(args, "end_date", None) or None,
        )
        out_path = getattr(args, "out", None)
        if out_path:
            from pathlib import Path

            from core.persistence import atomic_write_text

            atomic_write_text(Path(out_path), csv_text)
            print(f"[OK] 成果を CSV で書き出しました: {out_path}")
        else:
            print(csv_text, end="")
        return

    # list（既定）
    if not getattr(args, "org_name", None):
        print("[ERROR] --org-name を指定してください（例: pantheon hq outcomes --org-name MyApp）")
        sys.exit(1)
    summary = store.summary_for_org(args.org_name)
    print(f"\n成果サマリ — {args.org_name}（{summary.event_count} 件）\n")
    if not summary.by_metric:
        print(
            "  記録なし。`pantheon hq outcomes record --org-name X --metric revenue --value 1000` で記録できます。"
        )
        return
    for metric, stats in sorted(summary.by_metric.items()):
        print(
            f"  {metric}: 合計 {stats['sum']:.1f} / 件数 {int(stats['count'])} / 直近 {stats['last']:.1f}"
        )
    print(f"\n  リーチ計: {summary.total_reach:.0f}  収益計: {summary.total_revenue:.0f}")


def register(subparsers: Any) -> None:
    hq_parser = subparsers.add_parser("hq", help="本社（HQ）による子 Organization の診断・構造介入")
    hq_sub = hq_parser.add_subparsers(dest="hq_command", required=True)

    diagnose_parser = hq_sub.add_parser("diagnose", help="全子 Organization を診断する")
    diagnose_parser.set_defaults(handler_name="cmd_hq_diagnose")

    propose_parser = hq_sub.add_parser("propose", help="弱みから構造介入提案を生成・保存する")
    propose_parser.add_argument(
        "--dry-run", action="store_true", help="保存せず生成内容だけ表示する"
    )
    propose_parser.set_defaults(handler_name="cmd_hq_propose")

    apply_parser = hq_sub.add_parser("apply", help="構造介入提案を Policy+PreTask 経由で適用する")
    apply_parser.add_argument("proposal_id", help="提案 ID（先頭一致可）")
    apply_parser.add_argument(
        "--org-name", required=True, help="提案が保存されている Organization 名"
    )
    apply_parser.add_argument("--yes", action="store_true", help="確認を省略して適用する")
    apply_parser.set_defaults(handler_name="cmd_hq_apply")

    outcomes_parser = hq_sub.add_parser("outcomes", help="成果イベントの記録/一覧（Phase 8）")
    outcomes_sub = outcomes_parser.add_subparsers(dest="outcomes_action", required=False)

    rec = outcomes_sub.add_parser("record", help="成果イベントを記録する")
    rec.add_argument("--org-name", required=True, help="対象 Organization 名")
    rec.add_argument(
        "--metric", required=True, help="指標名（例: revenue, impressions, conversions）"
    )
    rec.add_argument("--value", type=float, required=True, help="値")
    rec.add_argument("--unit", default="", help="単位（任意）")
    rec.add_argument("--source", default="", help="出所（任意）")
    rec.add_argument("--note", default="", help="メモ（任意）")
    rec.set_defaults(handler_name="cmd_hq_outcomes")

    lst = outcomes_sub.add_parser("list", help="成果サマリを表示する")
    lst.add_argument("--org-name", required=True, help="対象 Organization 名")
    lst.set_defaults(handler_name="cmd_hq_outcomes")

    imp = outcomes_sub.add_parser(
        "import",
        help="CSV/JSON から成果イベントを一括取り込みする（ダッシュボードのエクスポート等）",
    )
    imp.add_argument("path", help="取り込むファイル（.csv または .json）")
    imp.add_argument(
        "--org-name", default="", help="org_name 列が無い行に使う既定の Organization 名"
    )
    imp.set_defaults(handler_name="cmd_hq_outcomes")

    exp = outcomes_sub.add_parser("export", help="成果イベントを CSV で書き出す（外部分析用）")
    exp.add_argument("--org-name", help="対象 Organization（省略で全件）")
    exp.add_argument("--metric", help="metric で絞り込み（省略で全 metric）")
    exp.add_argument("--start-date", dest="start_date", help="開始日 YYYY-MM-DD（含む）")
    exp.add_argument("--end-date", dest="end_date", help="終了日 YYYY-MM-DD（含む）")
    exp.add_argument("--out", help="出力ファイルパス（省略で標準出力）")
    exp.set_defaults(handler_name="cmd_hq_outcomes")

    # `hq outcomes --org-name X`（サブコマンド省略時）も list として扱う
    outcomes_parser.add_argument("--org-name", help="対象 Organization 名（list 既定）")
    outcomes_parser.set_defaults(handler_name="cmd_hq_outcomes")
