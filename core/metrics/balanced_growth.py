"""
KPI とバランス成長メトリクス（Core + Organization）

Core（中核）と各 Organization の健全な成長を定量的に測る仕組み。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from core.models.organization import GroupHQState, Organization, OrganizationMetrics


@dataclass
class GroupMetrics:
    """Core 視点のバランス成長指標"""
    total_organizations: int
    active_organizations: int
    avg_autonomy: float
    avg_improvement_velocity: float
    group_health_score: float
    balance_score: float
    total_pending_proposals: int
    weakest_organization: str | None
    strongest_organization: str | None


def calculate_organization_metrics(
    organization: Organization,
    pending_proposals_count: int = 0,
    recent_review_scores: List[float] | None = None,
) -> OrganizationMetrics:
    """個別Organizationの成長指標を計算"""
    recent_review_scores = recent_review_scores or []

    avg_review = (
        sum(recent_review_scores) / len(recent_review_scores)
        if recent_review_scores else 5.0
    )

    health = (
        organization.autonomy_score * 0.4 +
        organization.improvement_velocity * 0.3 +
        avg_review * 0.3
    )

    return OrganizationMetrics(
        organization_id=str(organization.id),
        name=organization.name,
        autonomy_score=organization.autonomy_score,
        improvement_velocity=organization.improvement_velocity,
        avg_review_score=round(avg_review, 2),
        pending_proposals_count=pending_proposals_count,
        health_score=round(health, 1),
    )


def calculate_group_metrics(
    hq_state: GroupHQState,
    organization_metrics: List[OrganizationMetrics],
) -> GroupMetrics:
    """グループ全体のバランス成長メトリクスを計算"""
    if not organization_metrics:
        return GroupMetrics(
            total_organizations=0,
            active_organizations=0,
            avg_autonomy=0,
            avg_improvement_velocity=0,
            group_health_score=50.0,
            balance_score=50.0,
            total_pending_proposals=0,
            weakest_organization=None,
            strongest_organization=None,
        )

    total_orgs = len(organization_metrics)
    active_orgs = sum(1 for m in organization_metrics if m.health_score > 40)

    avg_autonomy = sum(m.autonomy_score for m in organization_metrics) / total_orgs
    avg_velocity = sum(m.improvement_velocity for m in organization_metrics) / total_orgs
    avg_health = sum(m.health_score for m in organization_metrics) / total_orgs

    total_pending = sum(m.pending_proposals_count for m in organization_metrics)

    weakest = min(organization_metrics, key=lambda m: m.health_score)
    strongest = max(organization_metrics, key=lambda m: m.health_score)

    # バランススコア（分散が小さいほど高い）
    variance = sum((m.health_score - avg_health) ** 2 for m in organization_metrics) / total_orgs
    balance_score = max(0, 100 - variance * 2)

    return GroupMetrics(
        total_organizations=total_orgs,
        active_organizations=active_orgs,
        avg_autonomy=round(avg_autonomy, 1),
        avg_improvement_velocity=round(avg_velocity, 1),
        group_health_score=round(avg_health, 1),
        balance_score=round(balance_score, 1),
        total_pending_proposals=total_pending,
        weakest_organization=weakest.name,
        strongest_organization=strongest.name,
    )


def get_improvement_priority_score(metrics: OrganizationMetrics) -> float:
    """このOrganizationを今改善すべき優先度スコアを計算"""
    score = (
        (100 - metrics.health_score) * 0.5 +
        metrics.pending_proposals_count * 5 +
        (100 - metrics.autonomy_score) * 0.3
    )
    return round(score, 1)
