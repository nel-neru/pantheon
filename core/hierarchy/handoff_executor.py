"""承認済みクロス Org ハンドオフの自動実行（拡張: フライホイール actuate）。

承認済み（``approved``）で未消費のハンドオフを受け手 org のブリーフ提案へ実体化し、
状態を ``consumed`` まで前進させる。承認したハンドオフが「受け手 org の着手待ち」で
止まる摩擦を解消し、集客→制作→収益化のクロス Org フローを push 駆動にする。

HITL 安全性: ``approved``（既に承認ゲートを通過済み）のものだけを対象にし、生成する
content_asset ブリーフ提案は受け手 org 側で human_required（通常の proposal apply で適用）。
外部送信・課金は伴わない。決定論（ブリーフは型テンプレ・LLM 非依存）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def execute_approved_handoffs(
    *,
    psm: Any = None,
    target_org: Optional[str] = None,
    mark_consumed: bool = True,
) -> List[Dict[str, Any]]:
    """承認済み(approved)・未消費のハンドオフを実体化し consumed へ進める。

    ``target_org`` 指定でその受け手のみ。未実体化なら ``materialize_handoff`` でブリーフ提案を
    生成し ``record_materialization``、その後 ``mark_consumed``（``mark_consumed=False`` で実体化のみ）。
    受け手 org 未登録/repo 未設定で実体化不可なら status=``no_target`` で記録しスキップ。

    Returns: ``[{handoff_id, target_org, status, proposal_id}]``（status: consumed/materialized/no_target）。
    """
    if psm is None:
        from core.platform.state import PlatformStateManager

        psm = PlatformStateManager()

    from core.hierarchy.org_handoff import (
        HANDOFF_APPROVED,
        OrgHandoffStore,
        materialize_handoff,
    )

    store = OrgHandoffStore(platform_home=psm.platform_home)
    approved = store.list_handoffs(status=HANDOFF_APPROVED)
    if target_org:
        approved = [h for h in approved if h.target_org == target_org]

    results: List[Dict[str, Any]] = []
    for handoff in approved:
        proposal_id = getattr(handoff, "materialized_ref", "") or ""
        if not proposal_id:
            proposal = materialize_handoff(handoff, psm=psm)
            if proposal is None:
                results.append(
                    {
                        "handoff_id": handoff.handoff_id,
                        "target_org": handoff.target_org,
                        "status": "no_target",
                        "proposal_id": None,
                    }
                )
                continue
            proposal_id = str(proposal.id)
            store.record_materialization(handoff.handoff_id, proposal_id)
        status = "materialized"
        if mark_consumed:
            store.mark_consumed(handoff.handoff_id, consumed_ref=proposal_id)
            status = "consumed"
        results.append(
            {
                "handoff_id": handoff.handoff_id,
                "target_org": handoff.target_org,
                "status": status,
                "proposal_id": proposal_id,
            }
        )
    return results
