"""
Organization Factory

YAML テンプレートから Division / Team / SpecialistAgent 構造を持つ
Organization を動的に作成する。
config/departments/*.yaml を読み込んで構造を組み立てる。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import yaml

from core.models.organization import (
    AgentSkill,
    Division,
    DivisionType,
    Organization,
    OrganizationStatus,
    SpecialistAgent,
    Team,
)

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_PATH = (
    Path(__file__).parent.parent / "config" / "departments" / "meta_improvement.yaml"
)

# スキル名文字列 → AgentSkill の安全なマッピング
_SKILL_MAP: dict[str, AgentSkill] = {s.value: s for s in AgentSkill}

# DivisionType 文字列 → DivisionType
_DIVISION_TYPE_MAP: dict[str, DivisionType] = {d.value: d for d in DivisionType}


def _resolve_skill(skill_str: str) -> Optional[AgentSkill]:
    """文字列 → AgentSkill。マッピングにない場合は None を返す。"""
    return _SKILL_MAP.get(skill_str.lower())


def _resolve_division_type(type_str: str) -> DivisionType:
    return _DIVISION_TYPE_MAP.get(type_str, DivisionType.ORG_EVOLUTION)


def _normalize_repo_path(repo_path: str | Path | None) -> str | None:
    if repo_path in (None, ""):
        return None
    return str(repo_path)


def create_organization_from_template(
    name: str,
    purpose: str,
    template_path: Optional[Path] = None,
    status: OrganizationStatus = OrganizationStatus.INCUBATING,
    is_system: bool = False,
    repo_path: str | Path | None = None,
    isolation_level: str = "standard",
    allowed_path_scope: Optional[List[str]] = None,
) -> Organization:
    """
    YAML テンプレートから Organization を作成する。
    template_path が None の場合は meta_improvement.yaml を使用。
    """
    path = template_path or DEFAULT_TEMPLATE_PATH

    if not path.exists():
        logger.warning("Template not found: %s. Creating minimal organization.", path)
        return _create_minimal_organization(
            name,
            purpose,
            status,
            is_system,
            repo_path=repo_path,
            isolation_level=isolation_level,
            allowed_path_scope=allowed_path_scope,
        )

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    departments = data.get("departments", [])
    org = Organization(
        name=name,
        purpose=purpose,
        target_repo_path=_normalize_repo_path(repo_path),
        status=status,
        is_system=is_system,
        isolation_level=isolation_level,
        allowed_path_scope=list(allowed_path_scope or []),
    )

    for dept in departments:
        division = _build_division(dept)
        org.add_division(division)

    return org


def create_default_organization(
    name: str,
    purpose: str,
    status: OrganizationStatus = OrganizationStatus.INCUBATING,
    is_system: bool = False,
    repo_path: str | Path | None = None,
    isolation_level: str = "standard",
    allowed_path_scope: Optional[List[str]] = None,
) -> Organization:
    """最小構成の Organization を作成する（テンプレートなし）。"""
    return _create_minimal_organization(
        name,
        purpose,
        status,
        is_system,
        repo_path=repo_path,
        isolation_level=isolation_level,
        allowed_path_scope=allowed_path_scope,
    )


def _build_division(dept: dict) -> Division:
    div_type = _resolve_division_type(dept.get("type", "org_evolution"))
    division = Division(
        name=dept.get("name", "Unnamed Division"),
        type=div_type,
        mission=dept.get("mission", ""),
    )

    for team_data in dept.get("teams", []):
        team = _build_team(team_data, div_type)
        division.add_team(team)

    return division


def _build_team(team_data: dict, div_type: DivisionType) -> Team:
    team = Team(
        name=team_data.get("name", "Unnamed Team"),
        division_type=div_type,
        mission=team_data.get("mission", ""),
    )

    raw_skills: List[str] = team_data.get("required_skills", [])
    skills = [s for s in (_resolve_skill(r) for r in raw_skills) if s is not None]

    # 2〜3 スキルに正規化（仕様）
    if len(skills) >= 2:
        agent_skills = skills[:3]
    elif len(skills) == 1:
        agent_skills = [skills[0], AgentSkill.STRATEGIC_PLANNING]
    else:
        agent_skills = [AgentSkill.STRATEGIC_PLANNING, AgentSkill.DEEP_RESEARCH]

    agent = SpecialistAgent(
        name=f"{team.name} Specialist",
        skills=agent_skills,
        description=f"{team.mission} を担当する Specialist Agent",
    )
    team.agents.append(agent)
    return team


def _create_minimal_organization(
    name: str,
    purpose: str,
    status: OrganizationStatus,
    is_system: bool = False,
    repo_path: str | Path | None = None,
    isolation_level: str = "standard",
    allowed_path_scope: Optional[List[str]] = None,
) -> Organization:
    """テンプレートなしの最小構成 Organization。"""
    org = Organization(
        name=name,
        purpose=purpose,
        target_repo_path=_normalize_repo_path(repo_path),
        status=status,
        is_system=is_system,
        isolation_level=isolation_level,
        allowed_path_scope=list(allowed_path_scope or []),
    )
    division = Division(
        name="Core Team",
        type=DivisionType.ORG_EVOLUTION,
        mission="汎用的な組織運営と改善",
    )
    team = Team(
        name="General Team",
        division_type=DivisionType.ORG_EVOLUTION,
        mission=purpose,
    )
    agent = SpecialistAgent(
        name="General Specialist",
        skills=[AgentSkill.STRATEGIC_PLANNING, AgentSkill.DEEP_RESEARCH],
        description="汎用的な分析と改善を担当する Specialist Agent",
    )
    team.agents.append(agent)
    division.add_team(team)
    org.add_division(division)
    return org
