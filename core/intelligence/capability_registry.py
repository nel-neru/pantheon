"""
CapabilityRegistry — システム能力レジストリ (L-03)

システムが現在持っている全能力（Agent・Skill・Tool）を一覧管理する。
自律的自己拡張（テーマL）の基盤となるモジュール。

- agents/ 以下のすべての Agent クラスを自動スキャンして登録
- AgentSkill enum の全スキルを登録
- 追加された新能力を記録

`pantheon capabilities list` コマンドでシステムが自分の
持っている能力を把握できる状態を作る。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.paths import resource_root

logger = logging.getLogger(__name__)


@dataclass
class CapabilityEntry:
    """単一能力の記録。"""

    id: str
    name: str
    capability_type: str  # "agent" | "skill" | "tool" | "mcp_tool"
    description: str = ""
    source_file: str = ""
    skills: List[str] = field(default_factory=list)
    added_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    usage_count: int = 0
    last_used: Optional[str] = None
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "capability_type": self.capability_type,
            "description": self.description,
            "source_file": self.source_file,
            "skills": self.skills,
            "added_at": self.added_at,
            "usage_count": self.usage_count,
            "last_used": self.last_used,
            "is_active": self.is_active,
        }

    @property
    def is_available(self) -> bool:
        return self.is_active

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CapabilityEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class CapabilityRegistry:
    """
    システムの全能力を管理するレジストリ。

    CapabilityGapAnalyzer が「すでに持っているか」を確認し、
    ToolDesignAgent が「何が足りないか」を判断する際の基盤。
    """

    REGISTRY_FILE = "capability_registry.json"

    def __init__(
        self,
        platform_home: Optional[Path] = None,
        registry_file: Optional[Path] = None,
    ):
        from core.platform.state import get_platform_home

        self._home = Path(platform_home) if platform_home else get_platform_home()
        self._explicit_registry_file = Path(registry_file) if registry_file else None
        self._capabilities: Dict[str, CapabilityEntry] = {}
        self._load()

    @property
    def _registry_file(self) -> Path:
        return self._explicit_registry_file or (self._home / self.REGISTRY_FILE)

    # ------------------------------------------------------------------ #
    # スキャン・登録                                                       #
    # ------------------------------------------------------------------ #

    def scan_and_register_all(self, repo_root: Optional[Path] = None) -> int:
        """
        agents/ 以下のすべてのエージェントと AgentSkill を自動スキャンして登録する。
        Returns: 新規登録した能力の数
        """
        if repo_root is None:
            repo_root = resource_root()

        registered = 0
        registered += self._scan_agents(repo_root)
        registered += self._scan_skills()
        self._save()
        logger.info("CapabilityRegistry: %d new capabilities registered", registered)
        return registered

    def register(self, entry: CapabilityEntry) -> None:
        """能力を手動登録する（自己実装した新能力の追加に使用）。"""
        self._capabilities[entry.id] = entry
        self._save()

    def record_usage(self, capability_id: str) -> None:
        """能力が使用されたことを記録する。"""
        if capability_id in self._capabilities:
            cap = self._capabilities[capability_id]
            cap.usage_count += 1
            cap.last_used = datetime.now(timezone.utc).isoformat()
            self._save()

    # ------------------------------------------------------------------ #
    # 検索・参照                                                           #
    # ------------------------------------------------------------------ #

    def get(self, capability_id: str) -> Optional[CapabilityEntry]:
        return self._capabilities.get(capability_id)

    def list_all(self, capability_type: Optional[str] = None) -> List[CapabilityEntry]:
        entries = list(self._capabilities.values())
        if capability_type:
            entries = [e for e in entries if e.capability_type == capability_type]
        return sorted(entries, key=lambda e: e.name)

    def list_agents(self) -> List[CapabilityEntry]:
        return self.list_all("agent")

    def list_skills(self) -> List[CapabilityEntry]:
        return self.list_all("skill")

    def find_by_name(self, name: str) -> Optional[CapabilityEntry]:
        for cap in self._capabilities.values():
            if cap.name.lower() == name.lower():
                return cap
        return None

    def has_capability(self, name_or_id: str) -> bool:
        """能力が存在するかチェック（名前またはID）。"""
        return name_or_id in self._capabilities or self.find_by_name(name_or_id) is not None

    def get_unused_capabilities(
        self, days_threshold: int = 90, days: Optional[int] = None
    ) -> List[dict]:
        """しきい値より古い能力（=非推奨候補）を返す。

        各能力の「最終アクティビティ時刻」を ``last_used``（未使用なら ``added_at``）で測り、
        ``now - 最終アクティビティ >= threshold`` の能力だけを unused とみなす。
        したがって **一度も使われていない能力も、追加(``added_at``)から threshold 日以上
        経って初めて** unused に入る。scan 直後の新規能力（``usage_count==0`` だが追加が新しい）は
        報告しない（旧実装は ``usage_count==0`` を無条件 unused 扱いし、threshold を無視して
        ほぼ全件を返していた＝deprecation ワークフローのノイズ源だった）。

        ``days`` は ``days_threshold`` を上書きする後方互換エイリアス。
        タイムスタンプが解析不能な能力は、経過日数を判定できないため安全側で unused に含めない。
        """
        threshold = days if days is not None else days_threshold
        now = datetime.now(timezone.utc)
        unused: List[dict] = []
        for cap in self._capabilities.values():
            # 既に非推奨（is_active=False）にした能力は候補から除外する。さもないと
            # deprecate 済みの能力が毎回レポートに再出現して人間を再ナグしてしまう。
            if not cap.is_active:
                continue
            last_activity = cap.last_used or cap.added_at
            try:
                last_dt = datetime.fromisoformat(last_activity)
            except (ValueError, TypeError):
                # 経過日数が判定できない能力は非推奨候補にしない（安全側）。
                continue
            # naive な日時は UTC として扱う（aware な now との比較での TypeError を防ぐ）。
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            if (now - last_dt).days >= threshold:
                unused.append(cap.to_dict())
        return unused

    def mark_for_deprecation(self, capability_id: str) -> bool:
        """能力を非推奨（``is_active=False``）にして永続化する。

        明示的な人間操作（``capabilities --deprecate <id>`` ＝ HITL）から呼ばれる。
        マーカーは ``is_active`` 一本に正規化し、``_save`` で in-memory 状態を唯一の
        真実として書き戻す（旧実装は ``_save`` を使わず on-disk payload を手動パッチし、
        どの読取経路も参照しない ``deprecated`` キーを別途書いていた＝inert なノイズ）。
        非推奨化された能力は :meth:`get_unused_capabilities`・:meth:`format_for_agent`
        から除外される。存在しない id では何もせず ``False`` を返す。
        """
        cap = self._capabilities.get(capability_id)
        if cap is None:
            return False
        cap.is_active = False
        self._save()
        return True

    def format_for_agent(self) -> str:
        """エージェントのプロンプトに埋め込める形式で全能力を返す。"""
        lines = ["【現在のシステム能力一覧】"]
        for cap_type in ("agent", "skill", "tool"):
            # 非推奨（is_active=False）能力はエージェントへ宣伝しない（使うべきでないため）。
            entries = [e for e in self.list_all(cap_type) if e.is_active]
            if entries:
                label = {"agent": "エージェント", "skill": "スキル", "tool": "ツール"}.get(
                    cap_type, cap_type
                )
                lines.append(f"\n{label}:")
                for e in entries:
                    desc = f" — {e.description[:60]}" if e.description else ""
                    lines.append(f"  - {e.name}{desc}")
        return "\n".join(lines)

    def get_summary(self) -> Dict[str, Any]:
        entries = list(self._capabilities.values())
        return {
            "total": len(entries),
            "agents": len([e for e in entries if e.capability_type == "agent"]),
            "skills": len([e for e in entries if e.capability_type == "skill"]),
            "tools": len([e for e in entries if e.capability_type == "tool"]),
            "most_used": max(entries, key=lambda e: e.usage_count).name if entries else None,
        }

    # ------------------------------------------------------------------ #
    # 内部実装                                                             #
    # ------------------------------------------------------------------ #

    def _scan_agents(self, repo_root: Path) -> int:
        """
        AgentLoader (agents/definitions/*.yaml) からエージェントを登録する。

        Python ファイルのスキャンは廃止。YAML が唯一の定義ソース。
        """
        try:
            from core.loaders.agent_loader import AgentLoader

            loader = AgentLoader()
            registered = 0
            for defn in loader.all():
                cap_id = defn.capability_id
                if cap_id in self._capabilities:
                    # スキル情報が空なら補完
                    if not self._capabilities[cap_id].skills:
                        self._capabilities[cap_id].skills = list(defn.skills)
                    continue
                entry = CapabilityEntry(
                    id=cap_id,
                    name=defn.name,
                    capability_type="agent",
                    description=defn.description[:100] if defn.description else "",
                    source_file=f"agents/definitions/{defn.source_file}",
                    skills=list(defn.skills),
                )
                self._capabilities[cap_id] = entry
                registered += 1
            return registered
        except Exception as e:
            logger.warning("_scan_agents: AgentLoader failed: %s", e)
            return 0

    def _scan_skills(self) -> int:
        """
        SkillLoader (skills/*.yaml) からスキルを登録する。

        AgentSkill enum への依存は廃止。YAML が唯一の定義ソース。
        """
        try:
            from core.loaders.skill_loader import SkillLoader

            loader = SkillLoader()
            registered = 0
            for skill_def in loader.all():
                cap_id = f"skill:{skill_def.id}"
                if cap_id in self._capabilities:
                    continue
                entry = CapabilityEntry(
                    id=cap_id,
                    name=skill_def.name,
                    capability_type="skill",
                    description=skill_def.description[:100] if skill_def.description else "",
                )
                self._capabilities[cap_id] = entry
                registered += 1
            return registered
        except Exception as e:
            logger.warning("_scan_skills: SkillLoader failed: %s", e)
            return 0

    def _load(self) -> None:
        path = self._registry_file
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for d in data.get("capabilities", []):
                entry = CapabilityEntry.from_dict(d)
                self._capabilities[entry.id] = entry
        except Exception as e:
            logger.warning("CapabilityRegistry load failed: %s", e)

    def _save(self) -> None:
        path = self._registry_file
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "capabilities": [e.to_dict() for e in self._capabilities.values()],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ #
# ユーティリティ                                                       #
# ------------------------------------------------------------------ #
