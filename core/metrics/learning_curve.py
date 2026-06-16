"""
LearningCurveTracker — 学習曲線追跡 (B-06)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.platform.state import get_platform_home

SPARKLINE_CHARS = "▁▂▃▄▅▆▇█"


@dataclass
class LearningDataPoint:
    timestamp: str
    knowledge_count: int
    avg_proposal_quality: float
    accepted_count: int


class LearningCurveTracker:
    def __init__(self, platform_home=None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.data_file = self.platform_home / "learning_curve.jsonl"

    def record_snapshot(self, knowledge_count: int, avg_quality: float, accepted: int) -> None:
        point = LearningDataPoint(
            timestamp=datetime.now(timezone.utc).isoformat(),
            knowledge_count=int(knowledge_count),
            avg_proposal_quality=float(avg_quality),
            accepted_count=int(accepted),
        )
        with self.data_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(point), ensure_ascii=False) + "\n")

    def get_trend(self, limit: int = 30) -> list[LearningDataPoint]:
        if not self.data_file.exists():
            return []
        points: list[LearningDataPoint] = []
        for line in self.data_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                points.append(LearningDataPoint(**json.loads(line)))
            except Exception as exc:
                # 破損/不完全な行は黙殺せず観測可能にする（学習曲線の母数が静かに目減りするため）。
                from core.platform.state import warn_skipped_state_file

                warn_skipped_state_file(self.data_file, exc, kind="LearningDataPoint")
                continue
        return points[-limit:]

    def calculate_correlation(self) -> float:
        points = self.get_trend(limit=10_000)
        if len(points) < 3:
            return 0.0

        xs = [float(point.knowledge_count) for point in points]
        ys = [float(point.avg_proposal_quality) for point in points]
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        sum_sq_x = sum((x - mean_x) ** 2 for x in xs)
        sum_sq_y = sum((y - mean_y) ** 2 for y in ys)
        denominator = (sum_sq_x * sum_sq_y) ** 0.5
        if denominator == 0:
            return 0.0
        return numerator / denominator

    def format_for_cli(self) -> str:
        points = self.get_trend(limit=30)
        if not points:
            return ""

        values = [point.avg_proposal_quality for point in points]
        low = min(values)
        high = max(values)
        if high == low:
            return "▅" * len(values)

        scale = len(SPARKLINE_CHARS) - 1
        sparkline = []
        for value in values:
            index = round(((value - low) / (high - low)) * scale)
            sparkline.append(SPARKLINE_CHARS[int(index)])
        return "".join(sparkline)
