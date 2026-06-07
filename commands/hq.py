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

    require_api_key("pantheon hq apply")
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
