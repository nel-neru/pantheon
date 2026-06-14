"""
GoalLibrary — 達成済み目標のテンプレートライブラリ (M-06)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.platform.state import get_platform_home


@dataclass
class GoalTemplate:
    template_id: str
    goal_type: str
    description: str
    task_tree_summary: str
    avg_execution_time: float
    use_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class GoalLibrary:
    """Persist achieved goal templates for reuse."""

    def __init__(self, platform_home=None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.file_path = self.platform_home / "goal_library.json"

    def save_achieved_goal(
        self, goal_type: str, description: str, task_count: int, exec_time: float
    ) -> GoalTemplate:
        templates = self._load_all()
        template = GoalTemplate(
            template_id=f"goal:{uuid4().hex[:8]}",
            goal_type=goal_type,
            description=description,
            task_tree_summary=f"{task_count} tasks completed",
            avg_execution_time=float(exec_time),
        )
        templates.append(template)
        self._save_all(templates)
        return template

    def find_similar(self, goal_type: str, limit: int = 3) -> list[GoalTemplate]:
        templates = [tpl for tpl in self._load_all() if tpl.goal_type == goal_type]
        return sorted(templates, key=lambda item: item.use_count, reverse=True)[:limit]

    def record_use(self, template_id: str) -> None:
        templates = self._load_all()
        for template in templates:
            if template.template_id == template_id:
                template.use_count += 1
                break
        self._save_all(templates)

    def _load_all(self) -> list[GoalTemplate]:
        if not self.file_path.exists():
            return []
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        allowed = set(GoalTemplate.__dataclass_fields__)
        templates: list[GoalTemplate] = []
        for item in data.get("templates", []) if isinstance(data, dict) else []:
            if not isinstance(item, dict):
                continue
            try:
                templates.append(GoalTemplate(**{k: v for k, v in item.items() if k in allowed}))
            except Exception:  # 不正/レガシーレコードはスキップして全体を壊さない
                continue
        return templates

    def _save_all(self, templates: list[GoalTemplate]) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"templates": [asdict(template) for template in templates]}
        self.file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
