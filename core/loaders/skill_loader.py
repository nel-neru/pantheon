"""
SkillLoader — skills/*.yaml からスキル定義を読み込む

AgentSkillEngine のハードコードされたスキル定義を YAML ファイルに外部化する。
skills/ ディレクトリに新しい YAML ファイルを置くだけで新スキルを追加できる。

YAML フォーマット（例: skills/strategic_planning.yaml）:
    id: strategic_planning
    name: Strategic Planning
    persona: |
        あなたは長期戦略を立案するビジョナリーなアーキテクトです。
    focus: |
        短期的な解決策よりも…
    output_hint: |
        提案には…
    tags:
        - strategy
        - architecture
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from core.loaders.schema_support import validate_schema_version

logger = logging.getLogger(__name__)

# スキルの YAML で定義できるフィールド
_REQUIRED_FIELDS = {"id"}
_OPTIONAL_FIELDS = {"name", "description", "persona", "focus", "output_hint", "tags", "schema_version"}


class SkillDefinition:
    """YAML から読み込んだスキル定義。"""

    __slots__ = ("id", "name", "description", "persona", "focus", "output_hint", "tags", "schema_version")

    def __init__(self, data: dict[str, Any]):
        self.id: str = data["id"]
        self.schema_version: str = str(data.get("schema_version", ""))
        self.name: str = data.get("name", self.id)
        self.description: str = data.get("description", "")
        self.persona: str = data.get("persona", "").strip()
        self.focus: str = data.get("focus", "").strip()
        self.output_hint: str = data.get("output_hint", "").strip()
        self.tags: list[str] = data.get("tags", [])

    def to_prompt_addon(self) -> str:
        """AgentSkillEngine が注入するプロンプト文字列を生成する。"""
        parts = []
        if self.persona:
            parts.append(self.persona)
        if self.focus:
            parts.append(f"【注力点】\n{self.focus}")
        if self.output_hint:
            parts.append(f"【出力要件】\n{self.output_hint}")
        return "\n\n".join(parts)

    def __repr__(self) -> str:
        return f"SkillDefinition(id={self.id!r}, name={self.name!r})"


class SkillLoader:
    """
    skills/ ディレクトリの YAML ファイルからスキル定義を読み込む。

    使い方:
        loader = SkillLoader()
        skill = loader.get("strategic_planning")
        print(skill.to_prompt_addon())

        # 全スキルを取得
        for skill in loader.all():
            print(skill.id, skill.name)
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        if skills_dir is None:
            skills_dir = Path(__file__).parent.parent.parent / "skills"
        self._skills_dir = Path(skills_dir)
        self._cache: Dict[str, SkillDefinition] = {}
        self._loaded = False

    def _load_all(self) -> None:
        if self._loaded:
            return
        if not self._skills_dir.exists():
            logger.debug("SkillLoader: skills dir not found: %s", self._skills_dir)
            self._loaded = True
            return

        try:
            import yaml
        except ImportError:
            logger.warning("SkillLoader: PyYAML not installed, skipping YAML skill loading")
            self._loaded = True
            return

        for yaml_file in sorted(self._skills_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or "id" not in data:
                    logger.debug("Skipping %s: missing 'id' field", yaml_file.name)
                    continue
                data = dict(data)
                data["schema_version"] = validate_schema_version(data, yaml_file.name, kind="Skill definition")
                skill = SkillDefinition(data)
                self._cache[skill.id] = skill
                logger.debug("SkillLoader: loaded %s", skill.id)
            except Exception as e:
                logger.warning("SkillLoader: failed to load %s: %s", yaml_file.name, e)

        self._loaded = True
        logger.info("SkillLoader: %d skills loaded from %s", len(self._cache), self._skills_dir)

    def get(self, skill_id: str) -> Optional[SkillDefinition]:
        """スキル ID でスキル定義を取得する。"""
        self._load_all()
        return self._cache.get(skill_id)

    def all(self) -> list[SkillDefinition]:
        """全スキル定義を返す。"""
        self._load_all()
        return list(self._cache.values())

    def ids(self) -> list[str]:
        """登録されている全スキル ID を返す。"""
        self._load_all()
        return list(self._cache.keys())

    def reload(self) -> int:
        """キャッシュをクリアして再読み込みする。変更を反映したい場合に使う。"""
        self._cache.clear()
        self._loaded = False
        self._load_all()
        return len(self._cache)


# モジュールレベルのシングルトン（AgentSkillEngine から使う）
_default_loader: Optional[SkillLoader] = None


def get_skill_loader() -> SkillLoader:
    """デフォルト SkillLoader を返す（遅延初期化シングルトン）。"""
    global _default_loader
    if _default_loader is None:
        _default_loader = SkillLoader()
    return _default_loader
