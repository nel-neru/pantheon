"""
AgentLoader — agents/definitions/*.yaml からエージェント定義を読み込む

YAML ファイルだけで新エージェントを定義できる仕組み。
Python コードなしに name / skills / tools / behavior を定義すれば、
AgentFactory が自動的に GenericSkillAgent インスタンスを生成する。

YAML フォーマット（例: agents/definitions/strategic_planner.yaml）:
    name: StrategicPlanner
    description: 長期戦略の専門エージェント
    skills:
        - strategic_planning
        - org_design
    tools:
        - read_knowledge
        - search_codebase
    behavior: |
        組織とコードの構造を同一の視点で捉え…
    response_format:
        type: json
        fields:
            - result
            - key_findings
            - recommendations
            - confidence

新エージェントの追加方法:
    1. agents/definitions/ に新しい YAML ファイルを作成する
    2. name / skills / behavior を記述する
    3. repocorp で自動的に認識される（コード変更不要）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentDefinition:
    """
    YAML から読み込んだエージェント定義。

    この定義から AgentFactory が適切なエージェントを生成する。
    implementation フィールドがある場合は指定の Python クラスを使用し、
    ない場合は GenericSkillAgent が YAML の behavior / skills で振る舞いを決定する。
    """

    name: str
    description: str = ""
    skills: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    behavior: str = ""
    response_format: Dict[str, Any] = field(default_factory=dict)
    implementation: str = ""   # "module.path.ClassName" — Python実装を使う場合に指定
    source_file: str = ""

    @property
    def capability_id(self) -> str:
        """CapabilityRegistry の agent_id 形式（例: "agent:strategic_planner"）。"""
        stem = Path(self.source_file).stem if self.source_file else self.name.lower()
        return f"agent:{stem}"

    def build_system_prompt(self, skill_loader=None) -> str:
        """
        エージェントのシステムプロンプトを構築する。

        1. スキルごとのペルソナ・focus・output_hint（skills/*.yaml から）
        2. このエージェント固有の behavior

        Returns:
            完全なシステムプロンプト文字列
        """
        parts: List[str] = []

        # スキルのプロンプトアドオンを追加
        if skill_loader and self.skills:
            skill_sections = []
            for skill_id in self.skills:
                skill_def = skill_loader.get(skill_id)
                if skill_def:
                    addon = skill_def.to_prompt_addon()
                    if addon:
                        skill_sections.append(addon)
            if skill_sections:
                parts.append("\n\n---\n\n".join(skill_sections))

        # エージェント固有の振る舞い
        if self.behavior.strip():
            parts.append(f"【このエージェントの振る舞い】\n{self.behavior.strip()}")

        # レスポンス形式の指示
        if self.response_format:
            fmt_type = self.response_format.get("type", "json")
            fields = self.response_format.get("fields", [])
            if fmt_type == "json" and fields:
                fields_str = "\n".join(f'  "{f}": ...' for f in fields)
                parts.append(
                    f"【出力形式】\n以下の JSON 形式のみで返してください（コードブロック不要）:\n"
                    f"{{\n{fields_str}\n}}"
                )

        return "\n\n".join(parts) if parts else "あなたは専門的な AI エージェントです。"

    def __repr__(self) -> str:
        return (
            f"AgentDefinition(name={self.name!r}, "
            f"skills={self.skills!r}, "
            f"capability_id={self.capability_id!r})"
        )


class AgentLoader:
    """
    agents/definitions/ ディレクトリの YAML ファイルからエージェント定義を読み込む。

    使い方:
        loader = AgentLoader()

        # 全エージェント定義を取得
        for defn in loader.all():
            print(defn.name, defn.skills)

        # capability_id で取得
        defn = loader.get("agent:strategic_planner")

        # リロード（YAML ファイル変更後に反映）
        loader.reload()
    """

    def __init__(self, definitions_dir: Optional[Path] = None):
        if definitions_dir is None:
            definitions_dir = (
                Path(__file__).parent.parent.parent / "agents" / "definitions"
            )
        self._definitions_dir = Path(definitions_dir)
        self._cache: Dict[str, AgentDefinition] = {}  # capability_id → AgentDefinition
        self._loaded = False

    def _load_all(self) -> None:
        if self._loaded:
            return
        if not self._definitions_dir.exists():
            logger.debug("AgentLoader: definitions dir not found: %s", self._definitions_dir)
            self._loaded = True
            return

        try:
            import yaml
        except ImportError:
            logger.warning("AgentLoader: PyYAML not installed, skipping YAML agent loading")
            self._loaded = True
            return

        for yaml_file in sorted(self._definitions_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or "name" not in data:
                    logger.debug("Skipping %s: missing 'name' field", yaml_file.name)
                    continue
                defn = AgentDefinition(
                    name=data["name"],
                    description=data.get("description", ""),
                    skills=data.get("skills", []),
                    tools=data.get("tools", []),
                    behavior=data.get("behavior", ""),
                    response_format=data.get("response_format", {}),
                    implementation=data.get("implementation", ""),
                    source_file=yaml_file.name,
                )
                self._cache[defn.capability_id] = defn
                logger.debug("AgentLoader: loaded %s → %s", yaml_file.name, defn.capability_id)
            except Exception as e:
                logger.warning("AgentLoader: failed to load %s: %s", yaml_file.name, e)

        self._loaded = True
        logger.info(
            "AgentLoader: %d agent definitions loaded from %s",
            len(self._cache),
            self._definitions_dir,
        )

    def get(self, capability_id: str) -> Optional[AgentDefinition]:
        """capability_id でエージェント定義を取得する。"""
        self._load_all()
        return self._cache.get(capability_id)

    def all(self) -> List[AgentDefinition]:
        """全エージェント定義を返す。"""
        self._load_all()
        return list(self._cache.values())

    def capability_ids(self) -> List[str]:
        """登録されている全 capability_id を返す。"""
        self._load_all()
        return list(self._cache.keys())

    def reload(self) -> int:
        """キャッシュをクリアして YAML を再読み込みする。"""
        self._cache.clear()
        self._loaded = False
        self._load_all()
        return len(self._cache)


# モジュールレベルのシングルトン
_default_loader: Optional[AgentLoader] = None


def get_agent_loader() -> AgentLoader:
    """デフォルト AgentLoader を返す（遅延初期化シングルトン）。"""
    global _default_loader
    if _default_loader is None:
        _default_loader = AgentLoader()
    return _default_loader
