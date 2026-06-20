"""Goal 再計画フィードバックループ（拡張: 目標を一発勝負から反復収束へ）。

``GoalVerifier`` が達成度 < しきい値（既定 70%）を報告したら、未達基準・推奨事項・改訂方針を
まとめた **再計画 meta 提案**（``is_meta=True``）を生成する純粋関数。承認インボックス（Meta-Improvement
組織）に積まれ、オペレーターが承認してから再実行する想定（HITL 維持）。無限ループ防止に
``replan_cycle`` ガードを持つ。決定論・LLM 非依存。
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import NAMESPACE_URL, uuid5

# 達成度がこの % 未満なら再計画を提案する（GoalVerifier.ACHIEVEMENT_THRESHOLD と整合）。
REPLAN_THRESHOLD = 70.0
# 同一ゴールの再計画サイクル上限（無限ループ防止）。
MAX_REPLAN_CYCLES = 3
_REPLAN_NS = uuid5(NAMESPACE_URL, "pantheon.goals.replanning")


def propose_replanning(goal: Any, verification: Any, *, replan_cycle: int = 0) -> Optional["Any"]:
    """達成度が低いゴールに対する再計画 meta 提案を生成する（達成済み/上限超過は None）。

    ``goal`` は StructuredGoal、``verification`` は GoalVerificationResult（dict でも可）。
    ``replan_cycle`` が ``MAX_REPLAN_CYCLES`` 以上なら None（収束しないゴールを延々と再計画しない）。
    """
    from core.models.organization import ImprovementProposal

    achieved = bool(_field(verification, "overall_achieved", False))
    pct = float(_field(verification, "achievement_pct", 0.0) or 0.0)
    if achieved or pct >= REPLAN_THRESHOLD:
        return None
    if replan_cycle >= MAX_REPLAN_CYCLES:
        return None

    goal_id = str(_field(goal, "goal_id", "") or _field(verification, "goal_id", ""))
    description = str(
        _field(goal, "description", "") or _field(verification, "goal_description", "")
    )
    unmet = list(_field(verification, "unmet_criteria", []) or [])
    recommendations = list(_field(verification, "recommendations", []) or [])

    next_cycle = replan_cycle + 1
    dedupe_key = f"replan:{goal_id}:{next_cycle}"
    body = [
        f"目標『{description}』の達成度が {pct:.0f}%（しきい値 {REPLAN_THRESHOLD:.0f}% 未満）。",
        f"再計画サイクル {next_cycle}/{MAX_REPLAN_CYCLES}。",
    ]
    if unmet:
        body.append("未達の成功基準:")
        body.extend(f"  - {c}" for c in unmet[:5])
    if recommendations:
        body.append("推奨事項:")
        body.extend(f"  - {r}" for r in recommendations[:5])
    body.append("承認後、未達基準を重点化した改訂計画で再実行する想定（自動再実行はしない）。")

    return ImprovementProposal(
        review_id=uuid5(_REPLAN_NS, dedupe_key),
        priority="high" if pct < REPLAN_THRESHOLD / 2 else "medium",
        category="meta",
        title=f"[再計画] {description[:40]}（達成度 {pct:.0f}%）"[:120],
        description="\n".join(body),
        expected_impact=f"未達ゴールの反復収束（達成度 {pct:.0f}% → 再計画 {next_cycle} 巡目）",
        status="proposed",  # 人手承認ゲート（自動再実行しない）
        is_meta=True,
        dedupe_key=dedupe_key,
        target_kind="goal",
        source_org_name="GoalVerifier",
        intervention_spec={
            "kind": "goal_replanning",
            "goal_id": goal_id,
            "achievement_pct": pct,
            "unmet_criteria": unmet,
            "replan_cycle": next_cycle,
            "max_cycles": MAX_REPLAN_CYCLES,
        },
    )


def _field(obj: Any, key: str, default: Any) -> Any:
    if isinstance(obj, dict):
        value = obj.get(key, default)
    else:
        value = getattr(obj, key, default)
    return value if value is not None else default
