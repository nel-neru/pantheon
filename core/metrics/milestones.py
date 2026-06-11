"""
MilestoneTracker — 成長マイルストーン追跡 (C-10)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.platform.state import get_platform_home


@dataclass
class Milestone:
    milestone_id: str
    name: str
    description: str
    achieved_at: str = ""


MILESTONES = [
    Milestone("first_proposal", "初回提案採用", "最初の改善提案が承認されました！"),
    Milestone("score_50", "スコア50達成", "自律スコアが50を超えました！"),
    Milestone("score_80", "スコア80達成", "組織がMASTERステージに到達しました！"),
    Milestone("knowledge_10", "知識10件蓄積", "10件の知識が蓄積されました"),
    Milestone("stage_mature", "MATURE昇格", "組織がMATUREステージに到達しました！"),
]


class MilestoneTracker:
    def __init__(self, platform_home=None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)

    def check_and_award(
        self,
        org_name: str,
        autonomy_score: float,
        accepted_count: int,
        knowledge_count: int,
    ) -> list[Milestone]:
        achieved = {milestone.milestone_id: milestone for milestone in self.get_achieved(org_name)}
        newly_achieved: list[Milestone] = []
        now = datetime.now(timezone.utc).isoformat()

        for milestone in MILESTONES:
            if milestone.milestone_id in achieved:
                continue
            if not self._is_achieved(
                milestone.milestone_id, autonomy_score, accepted_count, knowledge_count
            ):
                continue
            awarded = Milestone(
                milestone_id=milestone.milestone_id,
                name=milestone.name,
                description=milestone.description,
                achieved_at=now,
            )
            achieved[awarded.milestone_id] = awarded
            newly_achieved.append(awarded)

        self._save(org_name, list(achieved.values()))
        return newly_achieved

    def get_achieved(self, org_name: str) -> list[Milestone]:
        path = self._path_for(org_name)
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        milestones: list[Milestone] = []
        for raw in payload:
            try:
                milestones.append(Milestone(**raw))
            except TypeError:
                continue
        return milestones

    def _path_for(self, org_name: str) -> Path:
        safe_name = org_name.replace("/", "_")
        return self.platform_home / f"milestones_{safe_name}.json"

    def _save(self, org_name: str, milestones: list[Milestone]) -> None:
        self._path_for(org_name).write_text(
            json.dumps([asdict(m) for m in milestones], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _is_achieved(
        self,
        milestone_id: str,
        autonomy_score: float,
        accepted_count: int,
        knowledge_count: int,
    ) -> bool:
        if milestone_id == "first_proposal":
            return accepted_count >= 1
        if milestone_id == "score_50":
            return autonomy_score >= 50
        if milestone_id == "score_80":
            return autonomy_score >= 80
        if milestone_id == "knowledge_10":
            return knowledge_count >= 10
        if milestone_id == "stage_mature":
            return autonomy_score >= 60
        return False
