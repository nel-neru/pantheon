"""
PersonaLoader — エージェントペルソナシステム (A-09)
config/personas/ のYAMLをエージェントに適用する
"""

from __future__ import annotations

from pathlib import Path

import yaml


class PersonaLoader:
    """config/personas/ 以下の persona YAML を読み込む。"""

    def __init__(self, personas_dir: Path = None):
        self.personas_dir = Path(personas_dir) if personas_dir else Path("config/personas")

    def load_persona(self, persona_name: str) -> dict | None:
        path = self._resolve_path(persona_name)
        if path is None or not path.exists():
            return None

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not data:
            return None
        return self._normalize_persona(persona_name, data)

    def get_system_prompt_addon(self, persona_name: str) -> str:
        persona = self.load_persona(persona_name)
        if not persona:
            return ""
        return str(persona.get("system_prompt_addon", ""))

    def list_personas(self) -> list[str]:
        if not self.personas_dir.exists():
            return []
        names = {path.stem for path in self.personas_dir.glob("*.yaml")}
        names.update(path.stem for path in self.personas_dir.glob("*.yml"))
        return sorted(names)

    def _resolve_path(self, persona_name: str) -> Path | None:
        yaml_path = self.personas_dir / f"{persona_name}.yaml"
        if yaml_path.exists():
            return yaml_path
        yml_path = self.personas_dir / f"{persona_name}.yml"
        if yml_path.exists():
            return yml_path
        return None

    def _normalize_persona(self, persona_name: str, data: dict) -> dict:
        if "persona" in data:
            persona = data.get("persona") or {}
            communication_style = data.get("communication_style") or {}
            return {
                "name": persona.get("name", persona_name),
                "role": persona.get("role", ""),
                "tone": communication_style.get("tone", ""),
                "focus_areas": list(data.get("focus_areas") or data.get("self_improvement_focus") or []),
                "system_prompt_addon": str(persona.get("description", "")).strip(),
            }

        return {
            "name": data.get("name", persona_name),
            "role": data.get("role", ""),
            "tone": data.get("tone", ""),
            "focus_areas": list(data.get("focus_areas") or []),
            "system_prompt_addon": str(data.get("system_prompt_addon", "")),
        }
