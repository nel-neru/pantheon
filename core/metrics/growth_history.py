"""
GrowthHistoryRecorder — 成長履歴記録 (C-06)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.platform.state import get_platform_home


@dataclass
class GrowthRecord:
    org_name: str
    timestamp: str
    autonomy_score: float
    improvement_velocity: float
    knowledge_count: int
    proposal_count: int
    accepted_count: int


class GrowthHistoryRecorder:
    def __init__(self, platform_home=None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.history_file = self.platform_home / "growth_history.jsonl"

    def record(self, org_name: str, **metrics) -> GrowthRecord:
        record = GrowthRecord(
            org_name=org_name,
            timestamp=datetime.now(timezone.utc).isoformat(),
            autonomy_score=float(metrics.get("autonomy_score", 0.0)),
            improvement_velocity=float(metrics.get("improvement_velocity", 0.0)),
            knowledge_count=int(metrics.get("knowledge_count", 0)),
            proposal_count=int(metrics.get("proposal_count", 0)),
            accepted_count=int(metrics.get("accepted_count", 0)),
        )
        with self.history_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        return record

    def get_history(self, org_name: str, limit: int = 30) -> list[GrowthRecord]:
        if not self.history_file.exists():
            return []
        records: list[GrowthRecord] = []
        for line in self.history_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = GrowthRecord(**json.loads(line))
            except Exception:
                continue
            if record.org_name == org_name:
                records.append(record)
        return records[-limit:]

    def get_trend_summary(self, org_name: str) -> str:
        records = self.get_history(org_name, limit=5)
        if len(records) < 2:
            return "横ばい"
        delta = records[-1].autonomy_score - records[0].autonomy_score
        if delta > 3:
            return "成長中"
        if delta < -3:
            return "低下中"
        return "横ばい"

    def predict_score(self, org_name: str, days_ahead: int = 30) -> float | None:
        records = self.get_history(org_name, limit=1000)
        if len(records) < 3:
            return None

        xs = self._build_x_values(records)
        ys = [record.autonomy_score for record in records]
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        denominator = sum((x - mean_x) ** 2 for x in xs)
        if denominator == 0:
            xs = [float(index) for index in range(len(records))]
            mean_x = sum(xs) / len(xs)
            denominator = sum((x - mean_x) ** 2 for x in xs)
            if denominator == 0:
                return max(0.0, min(100.0, ys[-1]))
        slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
        intercept = mean_y - slope * mean_x
        predicted_x = xs[-1] + float(days_ahead)
        predicted = intercept + slope * predicted_x
        return round(max(0.0, min(100.0, predicted)), 1)

    def _build_x_values(self, records: list[GrowthRecord]) -> list[float]:
        if not records:
            return []
        parsed: list[datetime] = []
        for record in records:
            try:
                parsed.append(datetime.fromisoformat(record.timestamp))
            except ValueError:
                parsed = []
                break
        if not parsed:
            return [float(index) for index in range(len(records))]
        start = parsed[0]
        values = [(item - start).total_seconds() / 86400 for item in parsed]
        if len(set(values)) == 1:
            return [float(index) for index in range(len(records))]
        return values
