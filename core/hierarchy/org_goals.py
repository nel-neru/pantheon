"""
OrgGoalManager — 組織目標管理 (E-09)
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
class OrgGoal:
    goal_id: str
    org_name: str
    description: str
    target_category: str
    priority: str = "medium"
    created_at: str = ""
    achieved_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class OrgGoalManager:
    DEFAULT_CATEGORIES = ["security", "performance", "maintainability", "testing", "knowledge"]

    def __init__(self, platform_home: Optional[Path] = None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.goals_path = self.platform_home / "org_goals.json"

    def set_goal(self, org_name: str, description: str, target_category: str) -> OrgGoal:
        goal = OrgGoal(
            goal_id=f"org-goal:{uuid4()}",
            org_name=org_name,
            description=description,
            target_category=target_category,
        )
        goals = self._load_goals()
        goals.append(goal)
        self._save_goals(goals)
        return goal

    def get_active_goals(self, org_name: str) -> list[OrgGoal]:
        return [
            goal
            for goal in self._load_goals()
            if goal.org_name == org_name and not goal.achieved_at
        ]

    def get_category_weights(self, org_name: str) -> dict[str, float]:
        weights = {category: 1.0 for category in self.DEFAULT_CATEGORIES}
        for goal in self.get_active_goals(org_name):
            weights[goal.target_category] = 2.0
        return weights

    def _load_goals(self) -> list[OrgGoal]:
        if not self.goals_path.exists():
            return []
        try:
            payload = json.loads(self.goals_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        return [OrgGoal(**item) for item in payload]

    def _save_goals(self, goals: list[OrgGoal]) -> None:
        self.goals_path.write_text(
            json.dumps([asdict(goal) for goal in goals], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
