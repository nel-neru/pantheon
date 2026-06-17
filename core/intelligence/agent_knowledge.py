"""
AgentKnowledgeAccumulator — エージェント専門知識蓄積 (A-06)
成功した分析パターンを自動保存し、再利用可能にする
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass
class SuccessPattern:
    pattern_id: str
    agent_id: str
    skill_name: str
    task_type: str
    pattern_summary: str
    success_score: float
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SuccessPattern":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class AgentKnowledgeAccumulator:
    """成功パターンをナレッジとローカルJSONLの両方へ蓄積する。"""

    def __init__(self, knowledge_manager=None, platform_home=None):
        from core.platform.state import get_platform_home

        self.knowledge_manager = knowledge_manager
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.pattern_file = self.platform_home / "agent_patterns.jsonl"

    def record_success(
        self,
        agent_id,
        skill_name,
        task_type,
        pattern_summary,
        score,
    ) -> SuccessPattern:
        pattern = SuccessPattern(
            pattern_id=str(uuid4()),
            agent_id=agent_id,
            skill_name=skill_name,
            task_type=task_type,
            pattern_summary=pattern_summary,
            success_score=float(score),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        if self.knowledge_manager is not None:
            self.knowledge_manager.save_insight(
                title=f"[{agent_id}] {task_type} success pattern",
                content=pattern_summary,
                tags=["agent_success", skill_name, task_type],
                source_org=agent_id,
                importance="high" if pattern.success_score >= 8 else "medium",
            )

        self._append_pattern(pattern)
        return pattern

    def get_patterns_for_task(self, task_type, skill_name=None, limit=5) -> list[SuccessPattern]:
        patterns = [
            pattern
            for pattern in self._load_patterns()
            if pattern.task_type == task_type
            and (skill_name is None or pattern.skill_name == skill_name)
        ]
        patterns.sort(key=lambda p: (p.success_score, p.created_at), reverse=True)
        return patterns[:limit]

    def _append_pattern(self, pattern: SuccessPattern) -> None:
        with self.pattern_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(pattern.to_dict(), ensure_ascii=False) + "\n")

    def _load_patterns(self) -> list[SuccessPattern]:
        if not self.pattern_file.exists():
            return []

        patterns: list[SuccessPattern] = []
        for line in self.pattern_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                patterns.append(SuccessPattern.from_dict(json.loads(line)))
            except Exception as exc:
                # 破損/不完全な行は黙殺せず観測可能にする（学習パターンの母数が静かに目減りするため）。
                from core.platform.state import warn_skipped_state_file

                warn_skipped_state_file(self.pattern_file, exc, kind="SuccessPattern")
                continue
        return patterns
