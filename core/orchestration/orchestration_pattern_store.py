"""
OrchestrationPatternStore — オーケストレーションパターン永続ライブラリ (N-05)

「どのオーケストレーションパターンが、どのタスク種別に対して
どれくらい有効だったか」を記録・学習するストア。

時間とともにパターン推薦精度が向上していく。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PatternRecord:
    """オーケストレーションパターンの実行記録。"""

    task_type: str
    pattern: str
    agent_ids: List[str]
    success: bool
    execution_time_ms: int = 0
    quality_score: float = 5.0
    notes: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class PatternStats:
    """パターンの集計統計。"""

    task_type: str
    pattern: str
    total_runs: int
    success_rate: float
    avg_quality: float
    recommended: bool = False


class OrchestrationPatternStore:
    """
    オーケストレーションパターンの実行実績を永続化して学習するストア。

    - 実行ごとに PatternRecord を保存
    - task_type × pattern の成功率・品質を集計
    - 最高成功率のパターンを「推奨パターン」として返す
    """

    STORE_FILE = "orchestration_patterns.json"
    # パターンを「推奨」できる最小実績数。これ未満の実績しか無いパターンは
    # まぐれ成功で well-tested なパターンを上書きしないよう推奨対象から外す。
    MIN_RUNS_FOR_RECOMMENDATION = 3

    def __init__(
        self,
        platform_home: Optional[Path] = None,
        store_file: Optional[Path] = None,
    ):
        from core.platform.state import get_platform_home

        self._home = Path(platform_home) if platform_home else get_platform_home()
        self._explicit_store_file = Path(store_file) if store_file else None
        self._records: List[PatternRecord] = []
        self._load()

    @property
    def _store_file(self) -> Path:
        return self._explicit_store_file or (self._home / self.STORE_FILE)

    def record(self, record: PatternRecord) -> None:
        """パターン実行記録を追加する。"""
        self._records.append(record)
        self._save()

    def get_best_pattern(self, task_type: str) -> Optional[str]:
        """
        指定タスク種別で最も成功率が高いパターンを返す。
        実績が3件未満のパターンは推奨対象にしない（該当が無ければ None →
        デフォルトを使うべき）。
        """
        stats = self.get_stats_for_task(task_type)
        # 推奨できるのは「そのパターン自身」が3件以上の実績を積んだ場合のみ。
        # 旧実装は全パターン横断の最大 run 数で gate していたため、別パターンが
        # 3件に達した途端、1件だけ成功（success_rate=1.0）のパターンが
        # well-tested なパターンを打ち負かして選ばれてしまっていた（まぐれ1勝で
        # 学習結果が誤選択され、しかも再記録で under-tested なパターンに固着する）。
        eligible = [s for s in stats if s.total_runs >= self.MIN_RUNS_FOR_RECOMMENDATION]
        if not eligible:
            return None
        best = max(eligible, key=lambda s: (s.success_rate, s.avg_quality))
        return best.pattern

    def get_stats_for_task(self, task_type: str) -> List[PatternStats]:
        """タスク種別ごとのパターン統計を返す。"""
        filtered = [r for r in self._records if r.task_type == task_type]
        if not filtered:
            return []

        from collections import defaultdict

        grouped: Dict[str, List[PatternRecord]] = defaultdict(list)
        for rec in filtered:
            grouped[rec.pattern].append(rec)

        stats = []
        for pattern, records in grouped.items():
            successes = sum(1 for r in records if r.success)
            stats.append(
                PatternStats(
                    task_type=task_type,
                    pattern=pattern,
                    total_runs=len(records),
                    success_rate=round(successes / len(records), 3),
                    avg_quality=round(sum(r.quality_score for r in records) / len(records), 2),
                )
            )

        # 推奨パターンにフラグ（get_best_pattern と同じ実績ゲートで整合させる。
        # 実績不足のパターンを表示上「★推奨」と誤表示しないため、十分な実績を
        # 積んだパターンが無ければどれにもフラグを立てない）。
        eligible = [s for s in stats if s.total_runs >= self.MIN_RUNS_FOR_RECOMMENDATION]
        if eligible:
            best = max(eligible, key=lambda s: (s.success_rate, s.avg_quality))
            best.recommended = True

        return stats

    def get_overall_summary(self) -> Dict[str, Any]:
        """全タスク種別の集計サマリーを返す。"""
        task_types = set(r.task_type for r in self._records)
        return {
            "total_records": len(self._records),
            "task_types_covered": len(task_types),
            "by_task_type": {
                tt: len([r for r in self._records if r.task_type == tt])
                for tt in sorted(task_types)
            },
        }

    def _load(self) -> None:
        path = self._store_file
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            logger.warning("OrchestrationPatternStore load failed: %s", e)
            return
        raw = data.get("records", []) if isinstance(data, dict) else []
        if not isinstance(raw, list):
            logger.warning("OrchestrationPatternStore: records は list ではありません; 無視します")
            raw = []
        for d in raw:
            if not isinstance(d, dict):
                logger.warning("OrchestrationPatternStore: 非 dict レコードをスキップ")
                continue
            try:
                self._records.append(
                    PatternRecord(
                        **{k: v for k, v in d.items() if k in PatternRecord.__dataclass_fields__}
                    )
                )
            except Exception as e:  # 1 件の破損で後続レコードを失わない
                logger.warning("OrchestrationPatternStore: 不正レコードをスキップ: %s", e)
                continue

    def _save(self) -> None:
        path = self._store_file
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "records": [r.to_dict() for r in self._records],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
