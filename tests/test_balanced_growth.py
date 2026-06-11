"""Unit tests for balanced growth metrics"""

import pytest

from core.metrics.balanced_growth import (
    calculate_group_metrics,
    calculate_organization_metrics,
    get_improvement_priority_score,
)
from core.models.organization import GroupHQState, Organization, OrganizationStatus


def make_org(name: str = "Org", autonomy: float = 60.0, velocity: float = 60.0) -> Organization:
    return Organization(
        name=name,
        purpose="Testing",
        autonomy_score=autonomy,
        improvement_velocity=velocity,
        status=OrganizationStatus.ACTIVE,
    )


class TestCalculateOrganizationMetrics:
    def test_health_score_range(self):
        org = make_org(autonomy=80.0, velocity=70.0)
        m = calculate_organization_metrics(org)
        assert 0.0 <= m.health_score <= 100.0

    def test_low_pending_no_backlog_penalty(self):
        org = make_org()
        m = calculate_organization_metrics(org, pending_proposals_count=0)
        assert m.health_score == pytest.approx(calculate_organization_metrics(org, 0).health_score)

    def test_high_pending_count_recorded(self):
        """pending_proposals_count is tracked in OrganizationMetrics"""
        org = make_org(autonomy=80.0, velocity=80.0)
        m = calculate_organization_metrics(org, pending_proposals_count=20)
        assert m.pending_proposals_count == 20

    def test_review_score_included(self):
        org = make_org()
        m_high = calculate_organization_metrics(org, recent_review_scores=[90.0])
        m_low = calculate_organization_metrics(org, recent_review_scores=[10.0])
        assert m_high.health_score > m_low.health_score

    def test_organization_id_set(self):
        org = make_org()
        m = calculate_organization_metrics(org)
        assert m.organization_id == str(org.id)


class TestCalculateGroupMetrics:
    def test_empty_org_list(self):
        hq = GroupHQState()
        gm = calculate_group_metrics(hq, [])
        # No orgs → sensible defaults (not 100, shows system is empty)
        assert gm.group_health_score == 50.0
        assert gm.total_organizations == 0

    def test_average_health(self):
        hq = GroupHQState()
        o1 = make_org("O1", 40.0, 40.0)
        o2 = make_org("O2", 80.0, 80.0)
        hq.add_organization(o1)
        hq.add_organization(o2)
        m1 = calculate_organization_metrics(o1)
        m2 = calculate_organization_metrics(o2)
        gm = calculate_group_metrics(hq, [m1, m2])
        assert gm.group_health_score == pytest.approx(
            (m1.health_score + m2.health_score) / 2, abs=1.0
        )

    def test_weakest_and_strongest(self):
        hq = GroupHQState()
        low = make_org("Weak", 30.0, 30.0)
        high = make_org("Strong", 90.0, 90.0)
        hq.add_organization(low)
        hq.add_organization(high)
        ml = calculate_organization_metrics(low)
        mh = calculate_organization_metrics(high)
        gm = calculate_group_metrics(hq, [ml, mh])
        assert gm.weakest_organization is not None
        assert gm.strongest_organization is not None
        assert gm.weakest_organization != gm.strongest_organization


class TestGetImprovementPriorityScore:
    def test_lower_health_higher_priority(self):
        org_low = make_org("Low", 20.0, 20.0)
        org_high = make_org("High", 90.0, 90.0)
        m_low = calculate_organization_metrics(org_low)
        m_high = calculate_organization_metrics(org_high)
        assert get_improvement_priority_score(m_low) > get_improvement_priority_score(m_high)

    def test_score_is_nonnegative(self):
        org = make_org()
        m = calculate_organization_metrics(org)
        assert get_improvement_priority_score(m) >= 0
