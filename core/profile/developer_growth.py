"""
DeveloperGrowthTracker — 開発者成長追跡 (D-11)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.platform.state import get_platform_home


@dataclass
class DeveloperGrowthSnapshot:
    timestamp: str
    test_commit_ratio: float
    approval_rate: float
    focus_categories: list[str] = field(default_factory=list)


class DeveloperGrowthTracker:
    def __init__(self, platform_home: Optional[Path] = None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.growth_path = self.platform_home / "developer_growth.jsonl"

    def record_snapshot(
        self,
        test_ratio: float,
        approval_rate: float,
        focus_categories: list[str],
    ) -> DeveloperGrowthSnapshot:
        snapshot = DeveloperGrowthSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            test_commit_ratio=float(test_ratio),
            approval_rate=float(approval_rate),
            focus_categories=list(focus_categories),
        )
        with self.growth_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(snapshot), ensure_ascii=False) + "\n")
        return snapshot

    def get_growth_trend(self, limit: int = 10) -> list[DeveloperGrowthSnapshot]:
        if not self.growth_path.exists():
            return []

        snapshots: list[DeveloperGrowthSnapshot] = []
        for line in self.growth_path.read_text(encoding="utf-8").splitlines()[-limit:]:
            if not line.strip():
                continue
            try:
                snapshots.append(DeveloperGrowthSnapshot(**json.loads(line)))
            except Exception:
                continue
        return snapshots

    def summarize_growth(self) -> str:
        snapshots = self.get_growth_trend(limit=100)
        if not snapshots:
            return "成長記録がまだありません"
        if len(snapshots) == 1:
            snapshot = snapshots[0]
            return (
                f"初回記録: テスト比率 {snapshot.test_commit_ratio:.2f}、"
                f"承認率 {snapshot.approval_rate:.2f}"
            )

        oldest = snapshots[0]
        newest = snapshots[-1]
        focus = ", ".join(newest.focus_categories) if newest.focus_categories else "なし"
        return (
            f"テスト比率 {oldest.test_commit_ratio:.2f}→{newest.test_commit_ratio:.2f}、"
            f"承認率 {oldest.approval_rate:.2f}→{newest.approval_rate:.2f}。"
            f"現在の注力領域: {focus}"
        )
