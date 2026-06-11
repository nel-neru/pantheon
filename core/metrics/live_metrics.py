"""
live_metrics — GUI 表示用の指標を「実リポジトリ状態」から都度計算する。

問題: ``Organization.autonomy_score`` (既定 40.0) / ``improvement_velocity`` (既定 50.0) は
作成時の静的デフォルトのまま実アプリでは更新されない（``ScoreUpdater`` の唯一の呼び出し経路が
未配線のデッドコード）。さらに ``balanced_growth`` の health は ``avg_review`` 定数 5.0 を常に使う。
結果として GUI の health/autonomy/velocity は全組織でほぼ定数になり、実データではない。

ここでは ``HealthCalculator`` / ``VelocityCalculator``（実装済みだがテストにしか結線されていない）を
使い、各組織の **実際の提案・決定履歴**（``RepoStateManager``）から health/autonomy/velocity を
読み取り時に計算する。これにより GUI の数値は実状態を反映する。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Tuple

from core.metrics.velocity import VelocityCalculator
from core.models.organization import is_active_improvement_proposal_status

# 「承認/適用済み」とみなす提案 status（pending/proposed/in_progress 以外で、棄却・失敗でないもの）。
_ACCEPTED_STATUSES = {"accepted", "approved", "done", "applied", "completed", "merged"}


def _is_accepted_proposal(proposal: dict[str, Any]) -> bool:
    return str(proposal.get("status", "")).lower() in _ACCEPTED_STATUSES


def _proposal_timestamp(proposal: dict[str, Any]) -> Optional[datetime]:
    # last_updated は status 変更時刻（=承認/適用時刻）。created_at（作成時刻）より優先し、
    # recency/last_improvement が「いつ改善が入ったか」を正しく反映するようにする。
    for key in (
        "updated_at",
        "applied_at",
        "decided_at",
        "last_updated",
        "created_at",
        "timestamp",
    ):
        value = proposal.get(key)
        if value:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            # naive な日時は UTC として扱う（aware と naive の比較/ソートでの TypeError を防ぐ）。
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
    return None


def _org_age_days(org: Any) -> float:
    created = getattr(org, "created_at", None)
    if created is None:
        return 1.0
    try:
        delta = datetime.now(timezone.utc) - created
        return max(1.0, delta.total_seconds() / 86400.0)
    except Exception:  # noqa: BLE001 - 壊れた日時でも 1 日として継続
        return 1.0


@dataclass
class LiveOrgMetrics:
    """実状態から計算した1組織の指標。"""

    health_score: float
    autonomy_score: float
    improvement_velocity: float
    pending_proposals: int
    accepted_ratio: float
    last_improvement: str


@dataclass
class LiveGroupMetrics:
    """実状態から計算したプラットフォーム横断指標。"""

    group_health_score: float
    balance_score: float
    total_organizations: int
    active_organizations: int
    weakest_organization: Optional[str]
    strongest_organization: Optional[str]
    total_pending_proposals: int


def compute_live_org_metrics(org: Any, state_manager: Any) -> LiveOrgMetrics:
    """組織の実際の改善提案履歴から health/autonomy/velocity を計算する。

    実承認シグナルは提案の ``status``（done/approved/applied=承認, pending/proposed=未対応,
    rejected/failed=棄却）。``record_decision`` は status を持たないため提案を一次情報とする。
    - autonomy_score: 決着した提案のうち承認/適用された割合 × 100（自律的に通せている度合い）
    - improvement_velocity: ``VelocityCalculator``（承認件数 / 組織年齢日数）
    - health_score: 50 + 承認率*30 − 未対応ペナルティ + 直近性ボーナス（HealthCalculator と同式）
    新規・無活動の組織は autonomy=0 / velocity=0 / health=50 となり「実際に活動が無い」ことを
    正しく反映する（捏造された 40/50/32.5 ではない）。
    """
    proposals = state_manager.get_all_improvement_proposals(limit=1000)
    pending = [p for p in proposals if is_active_improvement_proposal_status(p.get("status"))]
    decided = [p for p in proposals if not is_active_improvement_proposal_status(p.get("status"))]
    accepted = [p for p in decided if _is_accepted_proposal(p)]

    accepted_ratio = len(accepted) / max(1, len(decided))
    pending_count = len(pending)

    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    recency_bonus = 0
    for p in accepted:
        ts = _proposal_timestamp(p)
        if ts is not None and ts >= recent_cutoff:
            recency_bonus = 10
            break

    health = 50.0 + accepted_ratio * 30.0 - min(pending_count / 5.0, 20.0) + recency_bonus
    health = round(max(0.0, min(100.0, health)), 1)

    velocity = VelocityCalculator().calculate(len(accepted), _org_age_days(org))
    autonomy = round(accepted_ratio * 100.0, 1)
    last_improvement = ""
    if accepted:
        stamped = [(_proposal_timestamp(p), p) for p in accepted]
        stamped = [(t, p) for t, p in stamped if t is not None]
        if stamped:
            stamped.sort(key=lambda it: it[0])
            last_improvement = stamped[-1][0].isoformat()

    return LiveOrgMetrics(
        health_score=health,
        autonomy_score=autonomy,
        improvement_velocity=velocity,
        pending_proposals=pending_count,
        accepted_ratio=round(accepted_ratio, 3),
        last_improvement=last_improvement,
    )


def compute_live_group_metrics(items: List[Tuple[Any, LiveOrgMetrics]]) -> LiveGroupMetrics:
    """``(org, LiveOrgMetrics)`` の列から横断指標を計算する（実 health の平均・分散ベース）。"""
    if not items:
        # 組織ゼロは「データなし」。health=0/balance=100 のような矛盾した見かけを避け、
        # 両方 0 で一貫させる（GUI 側は total_organizations==0 で空状態を表示できる）。
        return LiveGroupMetrics(0.0, 0.0, 0, 0, None, None, 0)
    healths = [m.health_score for _, m in items]
    n = len(healths)
    mean_health = sum(healths) / n
    variance = sum((h - mean_health) ** 2 for h in healths) / n
    balance = max(0.0, 100.0 - variance * 2.0)
    active = sum(1 for h in healths if h > 40.0)
    weakest = min(items, key=lambda it: it[1].health_score)[0]
    strongest = max(items, key=lambda it: it[1].health_score)[0]
    total_pending = sum(m.pending_proposals for _, m in items)
    return LiveGroupMetrics(
        group_health_score=round(mean_health, 1),
        balance_score=round(balance, 1),
        total_organizations=n,
        active_organizations=active,
        weakest_organization=weakest.name,
        strongest_organization=strongest.name,
        total_pending_proposals=total_pending,
    )
