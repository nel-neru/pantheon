"""
OrganizationDesigner — LLM による組織設計エンジン (E-01~E-03)

目的テキストを入力するとLLMが最適なOrganization構造
（Division/Team/SpecialistAgent）を設計する。
設計結果はYAMLテンプレートとして保存・再利用できる。
"""

from __future__ import annotations

import inspect
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import yaml

from core.models.organization import (
    AgentSkill,
    Division,
    DivisionType,
    Organization,
    SpecialistAgent,
    Team,
)
from core.platform.state import get_platform_home


@dataclass
class AgentSpec:
    name: str
    skills: list[str]
    description: str


@dataclass
class TeamSpec:
    name: str
    mission: str
    agents: list[AgentSpec] = field(default_factory=list)


@dataclass
class DivisionSpec:
    name: str
    division_type: str
    mission: str
    teams: list[TeamSpec] = field(default_factory=list)


@dataclass
class OrganizationDesignSpec:
    spec_id: str
    purpose: str
    org_name: str
    divisions: list[DivisionSpec] = field(default_factory=list)
    created_at: str = ""
    template_name: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class OrganizationDesigner:
    def __init__(self, llm_client=None, platform_home: Optional[Path] = None):
        self.llm_client = llm_client
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.templates_dir = self.platform_home / "org_templates"
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def design(self, purpose: str, org_name: str = None) -> OrganizationDesignSpec:
        llm_spec = self._design_with_llm(purpose, org_name)
        if llm_spec is not None:
            return llm_spec

        target_name = org_name or self._default_org_name(purpose)
        purpose_lower = purpose.lower()
        divisions: list[DivisionSpec] = []

        if "security" in purpose_lower:
            divisions.append(
                self._make_division_spec(
                    name="SecurityDivision",
                    division_type=DivisionType.QUALITY_ASSURANCE.value,
                    mission="Security posture review and hardening.",
                    team_name="SecurityAuditTeam",
                    team_mission="Audit risks and recommend secure defaults.",
                    agent_name="SecurityAuditSpecialist",
                    skills=[AgentSkill.DEEP_RESEARCH.value, AgentSkill.TOOL_INTEGRATION.value],
                    description="Specialist focused on security review and remediation.",
                )
            )

        if "test" in purpose_lower:
            divisions.append(
                self._make_division_spec(
                    name="QualityDivision",
                    division_type=DivisionType.QUALITY_ASSURANCE.value,
                    mission="Raise product confidence through systematic validation.",
                    team_name="TestingTeam",
                    team_mission="Design, execute, and improve test coverage.",
                    agent_name="TestingSpecialist",
                    skills=[AgentSkill.CODEBASE_EXPLORATION.value, AgentSkill.DEEP_RESEARCH.value],
                    description="Specialist focused on testing strategy and validation.",
                )
            )

        if "performance" in purpose_lower:
            divisions.append(
                self._make_division_spec(
                    name="PerformanceDivision",
                    division_type=DivisionType.PERFORMANCE_OPTIMIZATION.value,
                    mission="Improve runtime efficiency and execution speed.",
                    team_name="OptimizationTeam",
                    team_mission="Identify bottlenecks and optimize critical flows.",
                    agent_name="PerformanceSpecialist",
                    skills=[
                        AgentSkill.PERFORMANCE_ANALYSIS.value,
                        AgentSkill.CODEBASE_EXPLORATION.value,
                    ],
                    description="Specialist focused on performance analysis and optimization.",
                )
            )

        if "knowledge" in purpose_lower:
            divisions.append(
                self._make_division_spec(
                    name="KnowledgeDivision",
                    division_type=DivisionType.KNOWLEDGE_MANAGEMENT.value,
                    mission="Keep organizational knowledge current and reusable.",
                    team_name="DocumentationTeam",
                    team_mission="Capture decisions and improve discoverability.",
                    agent_name="KnowledgeSpecialist",
                    skills=[AgentSkill.KNOWLEDGE_CURATION.value, AgentSkill.DEEP_RESEARCH.value],
                    description="Specialist focused on knowledge capture and documentation.",
                )
            )

        divisions.append(
            self._make_division_spec(
                name="CoreDivision",
                division_type=DivisionType.ORG_EVOLUTION.value,
                mission="Provide a resilient baseline organization structure.",
                team_name="GeneralTeam",
                team_mission=purpose,
                agent_name="GeneralSpecialist",
                skills=[AgentSkill.STRATEGIC_PLANNING.value, AgentSkill.DEEP_RESEARCH.value],
                description="Fallback specialist covering broad organizational needs.",
            )
        )

        return OrganizationDesignSpec(
            spec_id=str(uuid4()),
            purpose=purpose,
            org_name=target_name,
            divisions=divisions,
        )

    def instantiate(self, spec: OrganizationDesignSpec) -> Organization:
        organization = Organization(name=spec.org_name, purpose=spec.purpose)

        for division_spec in spec.divisions:
            division_type = self._resolve_division_type(division_spec.division_type)
            division = Division(
                name=division_spec.name,
                type=division_type,
                mission=division_spec.mission,
            )

            for team_spec in division_spec.teams:
                team = Team(
                    name=team_spec.name,
                    division_type=division_type,
                    mission=team_spec.mission,
                )

                agent_specs = team_spec.agents or [
                    self._default_agent_spec_for_division(division_type, team_spec.name)
                ]
                for agent_spec in agent_specs:
                    skills = self._resolve_skills(agent_spec.skills)
                    team.agents.append(
                        SpecialistAgent(
                            name=agent_spec.name,
                            skills=skills,
                            description=agent_spec.description,
                        )
                    )

                division.add_team(team)

            organization.add_division(division)

        return organization

    def save_as_template(self, spec: OrganizationDesignSpec, template_name: str) -> Path:
        spec.template_name = template_name
        path = self.templates_dir / f"{template_name}.yaml"
        path.write_text(
            yaml.safe_dump(asdict(spec), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return path

    def load_template(self, template_name: str) -> OrganizationDesignSpec:
        path = self.templates_dir / f"{template_name}.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not data.get("template_name"):
            data["template_name"] = template_name
        return self._spec_from_dict(data)

    def list_templates(self) -> list[str]:
        names = {path.stem for path in self.templates_dir.glob("*.yaml")}
        names.update(path.stem for path in self.templates_dir.glob("*.yml"))
        return sorted(names)

    def optimize_underperforming_teams(
        self,
        organization: Organization,
        threshold: float = 45.0,
    ) -> OrganizationDesignSpec:
        divisions: list[DivisionSpec] = []

        for division in organization.divisions:
            team_specs: list[TeamSpec] = []
            for team in division.teams:
                agent_specs = [
                    AgentSpec(
                        name=agent.name,
                        skills=[skill.value for skill in agent.skills],
                        description=agent.description,
                    )
                    for agent in team.agents
                ]

                avg_score = (
                    sum(agent.performance_score for agent in team.agents) / len(team.agents)
                    if team.agents
                    else 0.0
                )
                if avg_score < threshold:
                    agent_specs.append(
                        AgentSpec(
                            name=f"{team.name} Optimizer",
                            skills=[
                                AgentSkill.PERFORMANCE_ANALYSIS.value,
                                AgentSkill.DEEP_RESEARCH.value,
                            ],
                            description="Underperforming team optimization support.",
                        )
                    )

                team_specs.append(
                    TeamSpec(
                        name=team.name,
                        mission=team.mission,
                        agents=agent_specs,
                    )
                )

            divisions.append(
                DivisionSpec(
                    name=division.name,
                    division_type=division.type.value,
                    mission=division.mission,
                    teams=team_specs,
                )
            )

        return OrganizationDesignSpec(
            spec_id=f"optimized-{uuid4()}",
            purpose=organization.purpose,
            org_name=organization.name,
            divisions=divisions,
        )

    def _design_with_llm(
        self, purpose: str, org_name: Optional[str]
    ) -> Optional[OrganizationDesignSpec]:
        if self.llm_client is None or not hasattr(self.llm_client, "design_organization"):
            return None

        result = self.llm_client.design_organization(purpose=purpose, org_name=org_name)
        if inspect.isawaitable(result):
            return None
        if isinstance(result, OrganizationDesignSpec):
            return result
        if isinstance(result, dict):
            return self._spec_from_dict(result)
        return None

    def _default_org_name(self, purpose: str) -> str:
        seed = (purpose.strip() or "Adaptive").split()[0]
        return f"{seed.title()} Organization"

    def _make_division_spec(
        self,
        name: str,
        division_type: str,
        mission: str,
        team_name: str,
        team_mission: str,
        agent_name: str,
        skills: list[str],
        description: str,
    ) -> DivisionSpec:
        return DivisionSpec(
            name=name,
            division_type=division_type,
            mission=mission,
            teams=[
                TeamSpec(
                    name=team_name,
                    mission=team_mission,
                    agents=[
                        AgentSpec(
                            name=agent_name,
                            skills=skills,
                            description=description,
                        )
                    ],
                )
            ],
        )

    def _spec_from_dict(self, data: Dict[str, Any]) -> OrganizationDesignSpec:
        divisions = []
        for division_data in data.get("divisions", []):
            teams = []
            for team_data in division_data.get("teams", []):
                agents = [
                    AgentSpec(
                        name=agent_data.get("name", "Unnamed Agent"),
                        skills=list(agent_data.get("skills", [])),
                        description=agent_data.get("description", ""),
                    )
                    for agent_data in team_data.get("agents", [])
                ]
                teams.append(
                    TeamSpec(
                        name=team_data.get("name", "Unnamed Team"),
                        mission=team_data.get("mission", ""),
                        agents=agents,
                    )
                )
            divisions.append(
                DivisionSpec(
                    name=division_data.get("name", "Unnamed Division"),
                    division_type=division_data.get(
                        "division_type", DivisionType.ORG_EVOLUTION.value
                    ),
                    mission=division_data.get("mission", ""),
                    teams=teams,
                )
            )

        return OrganizationDesignSpec(
            spec_id=data.get("spec_id", str(uuid4())),
            purpose=data.get("purpose", ""),
            org_name=data.get("org_name", "Generated Organization"),
            divisions=divisions,
            created_at=data.get("created_at", ""),
            template_name=data.get("template_name", ""),
        )

    def _resolve_division_type(self, raw_value: str) -> DivisionType:
        normalized = (raw_value or "").strip().lower()
        for division_type in DivisionType:
            if normalized in {division_type.value.lower(), division_type.name.lower()}:
                return division_type
        return DivisionType.ORG_EVOLUTION

    def _resolve_skills(self, raw_skills: list[str]) -> list[AgentSkill]:
        resolved: list[AgentSkill] = []
        for raw_skill in raw_skills:
            normalized = (raw_skill or "").strip().lower()
            match = next(
                (
                    skill
                    for skill in AgentSkill
                    if normalized in {skill.value.lower(), skill.name.lower()}
                ),
                None,
            )
            resolved_skill = match or AgentSkill.DEEP_RESEARCH
            if resolved_skill not in resolved:
                resolved.append(resolved_skill)

        if not resolved:
            resolved = [AgentSkill.DEEP_RESEARCH, AgentSkill.STRATEGIC_PLANNING]
        elif len(resolved) == 1:
            fallback = AgentSkill.DEEP_RESEARCH
            if resolved[0] == fallback:
                fallback = AgentSkill.STRATEGIC_PLANNING
            resolved.append(fallback)

        return resolved[:3]

    def _default_agent_spec_for_division(
        self, division_type: DivisionType, team_name: str
    ) -> AgentSpec:
        skill_map = {
            DivisionType.QUALITY_ASSURANCE: [
                AgentSkill.DEEP_RESEARCH.value,
                AgentSkill.CODEBASE_EXPLORATION.value,
            ],
            DivisionType.PERFORMANCE_OPTIMIZATION: [
                AgentSkill.PERFORMANCE_ANALYSIS.value,
                AgentSkill.CODEBASE_EXPLORATION.value,
            ],
            DivisionType.KNOWLEDGE_MANAGEMENT: [
                AgentSkill.KNOWLEDGE_CURATION.value,
                AgentSkill.DEEP_RESEARCH.value,
            ],
            DivisionType.TOOL_INTEGRATION: [
                AgentSkill.TOOL_INTEGRATION.value,
                AgentSkill.PROMPT_ENGINEERING.value,
            ],
            DivisionType.AGENT_ARCHITECTURE: [
                AgentSkill.AGENT_WORKFLOW_DESIGN.value,
                AgentSkill.ORG_DESIGN.value,
            ],
            DivisionType.ORG_EVOLUTION: [
                AgentSkill.STRATEGIC_PLANNING.value,
                AgentSkill.ORG_DESIGN.value,
            ],
        }
        return AgentSpec(
            name=f"{team_name} Specialist",
            skills=skill_map.get(
                division_type, [AgentSkill.DEEP_RESEARCH.value, AgentSkill.STRATEGIC_PLANNING.value]
            ),
            description=f"Specialist supporting {team_name}.",
        )
