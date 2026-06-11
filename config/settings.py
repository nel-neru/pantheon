"""
Pantheon - 外部設定管理（YAML対応）

将来的に商品化を見据え、ルールや閾値をコードから分離して管理する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic import BaseModel, Field

try:
    from pydantic import ConfigDict
except ImportError:  # pragma: no cover - pydantic v1 compatibility
    ConfigDict = None


class StrictModel(BaseModel):
    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid")
    else:  # pragma: no cover - pydantic v1 compatibility

        class Config:
            extra = "forbid"


class ReviewStrictnessConfig(StrictModel):
    base_level: str = "very_strict"
    dynamic_adjustment: bool = True
    low_health_threshold: int = 50
    medium_health_threshold: int = 70


class HumanInLoopConfig(StrictModel):
    enabled: bool = True
    auto_approve_below_priority: str = "medium"
    timeout_minutes: int = 60


class ImprovementCycleConfig(StrictModel):
    max_cycles_per_sub: int = 5
    stop_if_no_improvement_for: int = 2
    default_max_cycles: int = 3


class MetricsConfig(StrictModel):
    health_score_weights: Dict[str, float] = Field(
        default_factory=lambda: {"autonomy": 0.4, "velocity": 0.3, "review_score": 0.3}
    )


class SelfImprovementConfig(StrictModel):
    review_strictness: ReviewStrictnessConfig = Field(default_factory=ReviewStrictnessConfig)
    human_in_loop: HumanInLoopConfig = Field(default_factory=HumanInLoopConfig)
    improvement_cycle: ImprovementCycleConfig = Field(default_factory=ImprovementCycleConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)


class PersonaConfig(StrictModel):
    name: str
    role: str
    tone: str = ""
    focus_areas: list[str] = Field(default_factory=list)
    system_prompt_addon: str = ""
    core_principles: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)


class NestedPersonaIdentityConfig(StrictModel):
    name: str
    role: str
    description: str = ""


class CommunicationStyleConfig(StrictModel):
    tone: str = ""
    language: str = ""
    decision_format: str = ""


class NestedPersonaFileConfig(StrictModel):
    persona: NestedPersonaIdentityConfig
    core_principles: list[str] = Field(default_factory=list)
    communication_style: CommunicationStyleConfig = Field(default_factory=CommunicationStyleConfig)
    allowed_tools: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    self_improvement_focus: list[str] = Field(default_factory=list)


class FlatPersonaFileConfig(StrictModel):
    name: str
    role: str
    tone: str = ""
    focus_areas: list[str] = Field(default_factory=list)
    system_prompt_addon: str = ""


class DepartmentTeamConfig(StrictModel):
    name: str
    mission: str
    required_skills: list[str] = Field(default_factory=list)


class DepartmentDefinitionConfig(StrictModel):
    name: str
    type: str
    mission: str
    reference_companies: list[str] = Field(default_factory=list)
    teams: list[DepartmentTeamConfig] = Field(default_factory=list)


class DepartmentTemplateConfig(StrictModel):
    departments: list[DepartmentDefinitionConfig] = Field(default_factory=list)


class SkillConfig(StrictModel):
    id: str
    name: str = ""
    description: str = ""
    persona: str = ""
    focus: str = ""
    output_hint: str = ""
    tags: list[str] = Field(default_factory=list)
    schema_version: str = ""
    focus_area: str = ""
    instructions: str = ""
    tools: list[str] = Field(default_factory=list)
    knowledge_refs: list[str] = Field(default_factory=list)


class AppConfig(StrictModel):
    self_improvement: SelfImprovementConfig = Field(default_factory=SelfImprovementConfig)
    personas: Dict[str, PersonaConfig] = Field(default_factory=dict)
    departments: Dict[str, DepartmentTemplateConfig] = Field(default_factory=dict)
    skills: Dict[str, SkillConfig] = Field(default_factory=dict)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def _iter_yaml_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    files = {path.resolve(): path for path in directory.glob("*.yaml")}
    files.update({path.resolve(): path for path in directory.glob("*.yml")})
    return [files[key] for key in sorted(files)]


def _normalize_persona_config(data: dict[str, Any]) -> PersonaConfig:
    if "persona" in data:
        nested = NestedPersonaFileConfig(**data)
        return PersonaConfig(
            name=nested.persona.name,
            role=nested.persona.role,
            tone=nested.communication_style.tone,
            focus_areas=list(nested.self_improvement_focus),
            system_prompt_addon=nested.persona.description,
            core_principles=list(nested.core_principles),
            allowed_tools=list(nested.allowed_tools),
            forbidden_actions=list(nested.forbidden_actions),
        )
    flat = FlatPersonaFileConfig(**data)
    return PersonaConfig(
        name=flat.name,
        role=flat.role,
        tone=flat.tone,
        focus_areas=list(flat.focus_areas),
        system_prompt_addon=flat.system_prompt_addon,
    )


def load_persona_configs(personas_dir: str | Path) -> dict[str, PersonaConfig]:
    directory = Path(personas_dir)
    configs: dict[str, PersonaConfig] = {}
    for path in _iter_yaml_files(directory):
        configs[path.stem] = _normalize_persona_config(_load_yaml_mapping(path))
    return configs


def load_department_configs(departments_dir: str | Path) -> dict[str, DepartmentTemplateConfig]:
    directory = Path(departments_dir)
    configs: dict[str, DepartmentTemplateConfig] = {}
    for path in _iter_yaml_files(directory):
        configs[path.stem] = DepartmentTemplateConfig(**_load_yaml_mapping(path))
    return configs


def load_skill_configs(skills_dir: str | Path) -> dict[str, SkillConfig]:
    directory = Path(skills_dir)
    configs: dict[str, SkillConfig] = {}
    for path in _iter_yaml_files(directory):
        skill = SkillConfig(**_load_yaml_mapping(path))
        configs[skill.id] = skill
    return configs


def _resolve_project_root(config_path: Path, project_root: str | Path | None = None) -> Path:
    if project_root is not None:
        return Path(project_root)
    resolved = config_path.resolve()
    if resolved.parent.name == "config":
        return resolved.parent.parent
    return Path.cwd()


def load_config(
    config_path: str | Path = "config/default.yaml",
    *,
    project_root: str | Path | None = None,
) -> AppConfig:
    """YAMLから設定を読み込み、関連設定ディレクトリも検証する。"""
    path = Path(config_path)
    data = _load_yaml_mapping(path) if path.exists() else {}
    root = _resolve_project_root(path, project_root=project_root)

    return AppConfig(
        self_improvement=SelfImprovementConfig(**data.get("self_improvement", {})),
        personas=load_persona_configs(root / "config" / "personas"),
        departments=load_department_configs(root / "config" / "departments"),
        skills=load_skill_configs(root / "skills"),
    )


config: AppConfig = load_config()
