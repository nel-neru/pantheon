"""
SkillProficiencyModel — スキル習熟度モデル (A-04)
スキルは使うほど上達する（1-100のproficiency score）
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class SkillProficiencyRecord:
    agent_id: str
    skill_name: str
    proficiency: float = 1.0
    use_count: int = 0
    success_count: int = 0
    last_used: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillProficiencyRecord":
        # 数値フィールドは破損 JSON（null/非数値）でも安全に coerce する（後続の比較/加算で
        # TypeError を起こしレコードが黙って消えるのを防ぐ）。文字列フィールドはそのまま。
        from core.persistence import coerce_float, coerce_int

        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        if "proficiency" in known:
            known["proficiency"] = coerce_float(known["proficiency"], 1.0)
        if "use_count" in known:
            known["use_count"] = coerce_int(known["use_count"], 0)
        if "success_count" in known:
            known["success_count"] = coerce_int(known["success_count"], 0)
        return cls(**known)


class SkillProficiencyManager:
    """エージェントごとのスキル習熟度を記録・永続化する。"""

    STORE_FILE = "skill_proficiency.json"

    def __init__(self, platform_home=None):
        from core.platform.state import get_platform_home

        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.store_file = self.platform_home / self.STORE_FILE
        self._records: dict[str, dict[str, SkillProficiencyRecord]] = self._deserialize(
            self._load()
        )

    def record_use(self, agent_id, skill_name, success: bool) -> SkillProficiencyRecord:
        agent_records = self._records.setdefault(agent_id, {})
        record = agent_records.get(skill_name)
        if record is None:
            record = SkillProficiencyRecord(agent_id=agent_id, skill_name=skill_name)
            agent_records[skill_name] = record

        record.use_count += 1
        if success:
            record.success_count += 1
            record.proficiency = min(100.0, record.proficiency + min(5.0, 100.0 / record.use_count))
        else:
            record.proficiency = max(1.0, record.proficiency - 2.0)
        record.last_used = datetime.now(timezone.utc).isoformat()
        self._save()
        return SkillProficiencyRecord.from_dict(record.to_dict())

    def get_proficiency(self, agent_id, skill_name) -> float:
        record = self._records.get(agent_id, {}).get(skill_name)
        return record.proficiency if record else 1.0

    def get_prompt_enhancement(self, agent_id, skill_name) -> str:
        proficiency = self.get_proficiency(agent_id, skill_name)
        if proficiency < 30:
            return "基本的な分析を丁寧に行ってください。"
        if proficiency <= 70:
            return "経験を活かした精度の高い分析を行ってください。"
        return "専門家レベルの深い洞察を提供してください。"

    def get_all_proficiencies(self, agent_id) -> dict[str, float]:
        return {
            skill_name: record.proficiency
            for skill_name, record in self._records.get(agent_id, {}).items()
        }

    def _load(self) -> dict[str, dict[str, dict[str, Any]]]:
        if not self.store_file.exists():
            return {}
        try:
            data = json.loads(self.store_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save(self) -> None:
        payload = {
            agent_id: {skill_name: record.to_dict() for skill_name, record in skills.items()}
            for agent_id, skills in self._records.items()
        }
        from core.persistence import atomic_write_text

        # 原子的に書く（スキル熟達データの partial write による静かな消失を防ぐ）。
        atomic_write_text(self.store_file, json.dumps(payload, ensure_ascii=False, indent=2))

    def _deserialize(
        self, data: dict[str, dict[str, dict[str, Any]]]
    ) -> dict[str, dict[str, SkillProficiencyRecord]]:
        records: dict[str, dict[str, SkillProficiencyRecord]] = {}
        for agent_id, skills in data.items():
            records[agent_id] = {
                skill_name: SkillProficiencyRecord.from_dict(record)
                for skill_name, record in skills.items()
            }
        return records
