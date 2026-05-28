"""
DeveloperGoalManager — 開発者目標設定 (D-08)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from core.platform.state import get_platform_home


@dataclass
class DeveloperGoal:
    goal_id: str
    description: str
    target_metric: str
    target_value: float
    current_value: float
    created_at: str
    achieved_at: str = ""


class DeveloperGoalManager:
    def __init__(self, platform_home: Optional[Path] = None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.goals_path = self.platform_home / "developer_goals.json"

    def set_goal(self, description: str, target_metric: str, target_value: float) -> DeveloperGoal:
        goal = DeveloperGoal(
            goal_id=f"goal:{uuid4()}",
            description=description,
            target_metric=target_metric,
            target_value=float(target_value),
            current_value=0.0,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        goals = self._load_goals()
        goals.append(goal)
        self._save_goals(goals)
        return goal

    def update_progress(self, goal_id: str, current_value: float) -> bool:
        goals = self._load_goals()
        newly_achieved = False
        for goal in goals:
            if goal.goal_id != goal_id:
                continue
            goal.current_value = float(current_value)
            if not goal.achieved_at and goal.current_value >= goal.target_value:
                goal.achieved_at = datetime.now(timezone.utc).isoformat()
                newly_achieved = True
            break
        self._save_goals(goals)
        return newly_achieved

    def get_active_goals(self) -> list[DeveloperGoal]:
        return [goal for goal in self._load_goals() if not goal.achieved_at]

    def get_priority_categories(self, goals: list[DeveloperGoal]) -> list[str]:
        keyword_map = {
            "security": ["security", "secure", "セキュリティ", "脆弱"],
            "performance": ["performance", "perf", "latency", "speed", "パフォーマンス", "高速"],
            "testing": ["test", "coverage", "qa", "品質", "テスト"],
            "maintainability": ["maintainability", "refactor", "readability", "保守", "リファクタ"],
            "knowledge": ["knowledge", "docs", "document", "ドキュメント", "ナレッジ"],
        }
        priorities: list[str] = []
        for category, keywords in keyword_map.items():
            for goal in goals:
                source = f"{goal.description} {goal.target_metric}".lower()
                if any(keyword.lower() in source for keyword in keywords):
                    priorities.append(category)
                    break
        return priorities

    def _load_goals(self) -> list[DeveloperGoal]:
        if not self.goals_path.exists():
            return []
        try:
            payload = json.loads(self.goals_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        return [DeveloperGoal(**item) for item in payload]

    def _save_goals(self, goals: list[DeveloperGoal]) -> None:
        self.goals_path.write_text(
            json.dumps([asdict(goal) for goal in goals], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
