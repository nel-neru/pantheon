#!/usr/bin/env python3
"""
Pantheon の YAML / 設定ファイルを検証するスクリプト。

Exit codes:
  0 - validation OK
  1 - validation errors found
  2 - script/runtime error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

REQUIRED_SKILL_KEYS = ("schema_version", "id", "name", "persona", "focus", "output_hint")
REQUIRED_AGENT_KEYS = (
    "schema_version",
    "name",
    "capability_id",
    "description",
    "skills",
    "tools",
    "behavior",
    "response_format",
)
REQUIRED_DEFAULT_KEYS = ("self_improvement",)


def _load_yaml(path: Path) -> tuple[Any | None, list[str]]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"{path}: file not found"]
    except yaml.YAMLError as exc:
        return None, [f"{path}: invalid YAML ({exc})"]
    except OSError as exc:
        return None, [f"{path}: cannot read file ({exc})"]
    return data, []


def _ensure_mapping(value: Any, path: Path, context: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{path}: {context} must be a mapping"]
    return []


def _ensure_sequence(
    value: Any, path: Path, context: str, *, min_items: int = 0, max_items: int | None = None
) -> list[str]:
    if not isinstance(value, list):
        return [f"{path}: {context} must be a list"]
    if len(value) < min_items:
        return [f"{path}: {context} must contain at least {min_items} item(s)"]
    if max_items is not None and len(value) > max_items:
        return [f"{path}: {context} must contain at most {max_items} item(s)"]
    return []


def _validate_required_keys(data: dict[str, Any], path: Path, keys: tuple[str, ...]) -> list[str]:
    errors: list[str] = []
    for key in keys:
        if key not in data:
            errors.append(f"{path}: missing required key '{key}'")
    return errors


def _validate_skill_file(path: Path) -> list[str]:
    data, errors = _load_yaml(path)
    if errors:
        return errors
    if not isinstance(data, dict):
        return [f"{path}: skill definition must be a mapping"]

    errors.extend(_validate_required_keys(data, path, REQUIRED_SKILL_KEYS))
    if "id" in data and data["id"] != path.stem:
        errors.append(f"{path}: id should match file name ('{path.stem}')")
    if "schema_version" in data and str(data["schema_version"]) != "1.0":
        errors.append(f"{path}: unsupported schema_version {data['schema_version']!r}")
    return errors


def _validate_agent_file(path: Path) -> list[str]:
    data, errors = _load_yaml(path)
    if errors:
        return errors
    if not isinstance(data, dict):
        return [f"{path}: agent definition must be a mapping"]

    errors.extend(_validate_required_keys(data, path, REQUIRED_AGENT_KEYS))
    if "capability_id" in data and not str(data["capability_id"]).startswith("agent:"):
        errors.append(f"{path}: capability_id must start with 'agent:'")
    if isinstance(data.get("skills"), list):
        skills = data["skills"]
        if not 2 <= len(skills) <= 3:
            errors.append(f"{path}: skills must contain 2-3 items")
    else:
        errors.append(f"{path}: skills must be a list")
    if isinstance(data.get("tools"), list) and not data["tools"]:
        errors.append(f"{path}: tools must not be empty")
    if isinstance(data.get("response_format"), dict):
        if "type" not in data["response_format"]:
            errors.append(f"{path}: response_format.type is required")
    return errors


def _validate_default_config(path: Path) -> list[str]:
    data, errors = _load_yaml(path)
    if errors:
        return errors
    if not isinstance(data, dict):
        return [f"{path}: default config must be a mapping"]

    errors.extend(_validate_required_keys(data, path, REQUIRED_DEFAULT_KEYS))
    self_improvement = data.get("self_improvement")
    if not isinstance(self_improvement, dict):
        errors.append(f"{path}: self_improvement must be a mapping")
        return errors

    for key in ("review_strictness", "human_in_loop", "improvement_cycle", "metrics"):
        if key not in self_improvement:
            errors.append(f"{path}: self_improvement.{key} is required")
    return errors


def _validate_department_file(path: Path) -> list[str]:
    data, errors = _load_yaml(path)
    if errors:
        return errors
    if not isinstance(data, dict):
        return [f"{path}: department config must be a mapping"]

    departments = data.get("departments")
    if not isinstance(departments, list) or not departments:
        return [f"{path}: departments must be a non-empty list"]

    for index, department in enumerate(departments):
        prefix = f"{path}: departments[{index}]"
        if not isinstance(department, dict):
            errors.append(f"{prefix} must be a mapping")
            continue
        for key in ("name", "type", "mission", "teams"):
            if key not in department:
                errors.append(f"{prefix}: missing required key '{key}'")
        teams = department.get("teams")
        if not isinstance(teams, list) or not teams:
            errors.append(f"{prefix}.teams must be a non-empty list")
            continue
        for team_index, team in enumerate(teams):
            team_prefix = f"{prefix}.teams[{team_index}]"
            if not isinstance(team, dict):
                errors.append(f"{team_prefix} must be a mapping")
                continue
            for key in ("name", "mission", "required_skills"):
                if key not in team:
                    errors.append(f"{team_prefix}: missing required key '{key}'")
            required_skills = team.get("required_skills")
            if isinstance(required_skills, list):
                if not 2 <= len(required_skills) <= 3:
                    errors.append(f"{team_prefix}.required_skills must contain 2-3 skills")
                if any(
                    not isinstance(skill, str) or not skill.strip() for skill in required_skills
                ):
                    errors.append(f"{team_prefix}.required_skills must contain non-empty strings")
            else:
                errors.append(f"{team_prefix}.required_skills must be a list")
    return errors


def _validate_persona_file(path: Path) -> list[str]:
    data, errors = _load_yaml(path)
    if errors:
        return errors
    if not isinstance(data, dict):
        return [f"{path}: persona config must be a mapping"]

    nested_persona = data.get("persona")
    if isinstance(nested_persona, dict):
        for key in ("name", "role", "description"):
            if key not in nested_persona:
                errors.append(f"{path}: persona.{key} is required")
    else:
        for key in ("name", "role", "system_prompt_addon"):
            if key not in data:
                errors.append(f"{path}: missing required key '{key}'")
    if "focus_areas" in data and not isinstance(data["focus_areas"], list):
        errors.append(f"{path}: focus_areas must be a list when provided")
    return errors


def validate_repository(root: Path) -> list[str]:
    errors: list[str] = []

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        for path in sorted(skills_dir.glob("*.yaml")):
            errors.extend(_validate_skill_file(path))

    agent_defs_dir = root / "agents" / "definitions"
    if agent_defs_dir.is_dir():
        for path in sorted(agent_defs_dir.glob("*.yaml")):
            errors.extend(_validate_agent_file(path))

    config_dir = root / "config"
    default_config = config_dir / "default.yaml"
    if default_config.exists():
        errors.extend(_validate_default_config(default_config))

    departments_dir = config_dir / "departments"
    if departments_dir.is_dir():
        for path in sorted(departments_dir.glob("*.yaml")):
            errors.extend(_validate_department_file(path))

    personas_dir = config_dir / "personas"
    if personas_dir.is_dir():
        for path in sorted(personas_dir.glob("*.yaml")):
            errors.extend(_validate_persona_file(path))

    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Pantheon YAML/config files.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root to validate (default: project root)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    root = args.root.resolve()
    errors = validate_repository(root)

    if errors:
        print(f"Config validation failed ({len(errors)} issue(s)):")
        for error in errors:
            print(f"- {error}")
        print("\nFix the files above and rerun: python scripts/validate_config.py")
        return 1

    print(f"Config validation passed for {root}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"Unexpected error during validation: {exc}", file=sys.stderr)
        sys.exit(2)
