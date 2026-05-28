"""
ActivityTracker — 作業時間パターン学習 (D-05)
CLIコマンドの実行時刻を記録し、作業パターンをプロファイルに保存する
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.platform.state import get_platform_home


DAY_NAMES = ["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"]


@dataclass
class ActivityRecord:
    timestamp: str
    command: str
    day_of_week: int
    hour: int


class ActivityTracker:
    def __init__(self, platform_home: Optional[Path] = None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.log_path = self.platform_home / "activity_log.jsonl"

    def record_activity(self, command: str) -> None:
        now = datetime.now()
        record = ActivityRecord(
            timestamp=now.isoformat(),
            command=command,
            day_of_week=now.weekday(),
            hour=now.hour,
        )
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def get_active_hours(self) -> list[int]:
        records = self._load_records()
        if not records:
            return []

        counts = Counter(record.hour for record in records)
        top_bucket_size = max(1, math.ceil(len(counts) * 0.25))
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        threshold = ranked[top_bucket_size - 1][1]
        return sorted(hour for hour, count in counts.items() if count >= threshold)

    def get_peak_day(self) -> str:
        records = self._load_records()
        if not records:
            return "不明"

        counts = Counter(record.day_of_week for record in records)
        peak_day, _ = min(counts.items(), key=lambda item: (-item[1], item[0]))
        return DAY_NAMES[peak_day]

    def get_activity_summary(self) -> str:
        active_hours = self.get_active_hours()
        if not active_hours:
            return "活動履歴がまだありません"
        return f"最もアクティブな時間帯: {self._format_hour_range(active_hours)}"

    def _load_records(self) -> list[ActivityRecord]:
        if not self.log_path.exists():
            return []

        records: list[ActivityRecord] = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(ActivityRecord(**json.loads(line)))
            except Exception:
                continue
        return records

    def _format_hour_range(self, hours: list[int]) -> str:
        if len(hours) == 1:
            return f"{hours[0]}時"
        if hours == list(range(hours[0], hours[-1] + 1)):
            return f"{hours[0]}-{hours[-1]}時"
        return ", ".join(f"{hour}時" for hour in hours)
