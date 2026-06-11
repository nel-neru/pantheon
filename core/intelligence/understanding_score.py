"""
UnderstandingScoreTracker — コードベース理解度スコア (K-12)
"""

from __future__ import annotations

import json
from pathlib import Path

from core.platform.state import get_platform_home


class UnderstandingScoreTracker:
    """Persist lightweight repo understanding scores."""

    def __init__(self, platform_home=None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.file_path = self.platform_home / "understanding_scores.json"

    def record_exploration(
        self, repo_name: str, files_explored: int, proposals_accepted: int, proposals_total: int
    ) -> None:
        data = self._load()
        record = data.get(repo_name, {})
        exploration_count = int(record.get("exploration_count", 0)) + 1
        score = (
            files_explored / 10
            + proposals_accepted / max(1, proposals_total) * 50
            + exploration_count * 5
        )
        data[repo_name] = {
            "score": min(100.0, round(score, 2)),
            "exploration_count": exploration_count,
            "files_explored": files_explored,
            "proposals_accepted": proposals_accepted,
            "proposals_total": proposals_total,
        }
        self._save(data)

    def get_score(self, repo_name: str) -> float:
        return float(self._load().get(repo_name, {}).get("score", 0.0))

    def get_all_scores(self) -> dict[str, float]:
        return {name: float(payload.get("score", 0.0)) for name, payload in self._load().items()}

    def _load(self) -> dict:
        if not self.file_path.exists():
            return {}
        try:
            return json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
