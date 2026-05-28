"""Unit tests for core data models"""
import pytest
from uuid import uuid4
from datetime import datetime

from core.models.organization import (
    AgentSkill,
    Division,
    DivisionType,
    GroupHQState,
    ImprovementProposal,
    Organization,
    OrganizationStatus,
    QualityReview,
    QualityScore,
    SpecialistAgent,
    Team,
)


class TestSpecialistAgent:
    def test_create_with_valid_skills(self):
        agent = SpecialistAgent(
            name="TestAgent",
            skills=[AgentSkill.STRATEGIC_PLANNING, AgentSkill.DEEP_RESEARCH],
        )
        assert agent.name == "TestAgent"
        assert len(agent.skills) == 2

    def test_min_skills_enforced(self):
        with pytest.raises(Exception):
            SpecialistAgent(name="Bad", skills=[AgentSkill.STRATEGIC_PLANNING])

    def test_max_skills_enforced(self):
        with pytest.raises(Exception):
            SpecialistAgent(
                name="Bad",
                skills=[
                    AgentSkill.STRATEGIC_PLANNING,
                    AgentSkill.DEEP_RESEARCH,
                    AgentSkill.TOOL_INTEGRATION,
                    AgentSkill.ORG_DESIGN,
                ],
            )

    def test_has_skill(self):
        agent = SpecialistAgent(
            name="A", skills=[AgentSkill.STRATEGIC_PLANNING, AgentSkill.DEEP_RESEARCH]
        )
        assert agent.has_skill(AgentSkill.STRATEGIC_PLANNING)
        assert not agent.has_skill(AgentSkill.ORG_DESIGN)

    def test_add_skill(self):
        agent = SpecialistAgent(
            name="A", skills=[AgentSkill.STRATEGIC_PLANNING, AgentSkill.DEEP_RESEARCH]
        )
        agent.add_skill(AgentSkill.ORG_DESIGN)
        assert len(agent.skills) == 3

    def test_add_skill_over_limit_ignored(self):
        agent = SpecialistAgent(
            name="A",
            skills=[AgentSkill.STRATEGIC_PLANNING, AgentSkill.DEEP_RESEARCH, AgentSkill.ORG_DESIGN],
        )
        agent.add_skill(AgentSkill.TOOL_INTEGRATION)
        assert len(agent.skills) == 3


class TestOrganization:
    def _make_org(self) -> Organization:
        return Organization(name="TestOrg", purpose="Testing")

    def test_create(self):
        org = self._make_org()
        assert org.name == "TestOrg"
        assert org.status == OrganizationStatus.INCUBATING

    def test_add_division(self):
        org = self._make_org()
        div = Division(name="Div1", type=DivisionType.ORG_EVOLUTION)
        org.add_division(div)
        assert len(org.divisions) == 1

    def test_get_all_agents(self):
        org = self._make_org()
        div = Division(name="Div1", type=DivisionType.ORG_EVOLUTION)
        team = Team(name="Team1", division_type=DivisionType.ORG_EVOLUTION)
        agent = SpecialistAgent(
            name="A", skills=[AgentSkill.STRATEGIC_PLANNING, AgentSkill.DEEP_RESEARCH]
        )
        team.agents.append(agent)
        div.add_team(team)
        org.add_division(div)
        assert len(org.get_all_agents()) == 1


class TestImprovementProposal:
    def test_has_file_path(self):
        p = ImprovementProposal(review_id=uuid4(), title="T", description="D")
        assert hasattr(p, "file_path")
        assert p.file_path == ""

    def test_file_path_set(self):
        p = ImprovementProposal(
            review_id=uuid4(), title="T", description="D", file_path="core/models.py"
        )
        assert p.file_path == "core/models.py"

    def test_default_status(self):
        p = ImprovementProposal(review_id=uuid4(), title="T", description="D")
        assert p.status == "proposed"

    def test_valid_statuses(self):
        for status in ("proposed", "pending", "in_progress", "done", "rejected", "failed", "cancelled"):
            p = ImprovementProposal(review_id=uuid4(), title="T", description="D", status=status)
            assert p.status == status


class TestGroupHQState:
    def test_recalculate_on_add(self):
        hq = GroupHQState()
        org = Organization(name="O1", purpose="P1", autonomy_score=60.0)
        hq.add_organization(org)
        assert hq.total_agents == 0
        assert hq.group_health_score == 60.0

    def test_multiple_orgs(self):
        hq = GroupHQState()
        hq.add_organization(Organization(name="O1", purpose="P1", autonomy_score=40.0))
        hq.add_organization(Organization(name="O2", purpose="P2", autonomy_score=80.0))
        assert hq.group_health_score == 60.0
