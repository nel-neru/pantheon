"""
CoevolutionGraph — 開発者とAI組織の共進化グラフ (D-12)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.platform.state import get_platform_home


class CoevolutionGraph:
    def __init__(self, platform_home: Optional[Path] = None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.graph_path = self.platform_home / "coevolution.jsonl"

    def record_coevolution_point(self, org_score: float, developer_approval_rate: float) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "org_score": float(org_score),
            "developer_approval_rate": float(developer_approval_rate),
        }
        with self.graph_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def get_both_trends(self, limit: int = 10) -> tuple[list[float], list[float]]:
        points = self._load_points()[-limit:]
        return (
            [point["org_score"] for point in points],
            [point["developer_approval_rate"] for point in points],
        )

    def format_ascii_chart(self) -> str:
        points = self._load_points()[-10:]
        if not points:
            return "共進化データがまだありません"

        lines = ["Org | Dev", "----------"]
        for index, point in enumerate(points, start=1):
            org_score = point["org_score"]
            dev_score = point["developer_approval_rate"]
            org_bar = "#" * max(1, int(round(org_score / 10)))
            dev_bar = "*" * max(1, int(round(dev_score / 10)))
            lines.append(
                f"{index:02d} {org_score:5.1f} {org_bar:<10} | {dev_score:5.1f} {dev_bar:<10}"
            )
        return "\n".join(lines)

    def _load_points(self) -> list[dict]:
        if not self.graph_path.exists():
            return []
        points: list[dict] = []
        for line in self.graph_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                # 破損行は黙殺せず観測可能にする（共進化グラフの母数が静かに目減りするため）。
                from core.platform.state import warn_skipped_state_file

                warn_skipped_state_file(self.graph_path, exc, kind="CoevolutionPoint")
                continue
            if (
                not isinstance(obj, dict)
                or "org_score" not in obj
                or "developer_approval_rate" not in obj
            ):
                continue
            try:
                obj["org_score"] = float(obj["org_score"])
                obj["developer_approval_rate"] = float(obj["developer_approval_rate"])
            except (TypeError, ValueError):
                continue
            points.append(obj)
        return points
