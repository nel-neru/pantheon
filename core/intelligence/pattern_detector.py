"""
OperationPatternDetector — 操作パターン検出器 (L-01)

エージェントやCLIが繰り返し実行している操作をログに記録し、
同一操作が3回以上繰り返された場合に「繰り返しパターン」としてフラグする。

CapabilityGapAnalyzer がこのパターンを見て
「自動化できる能力が不足している」を判断する基盤となる。
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

OPERATION_LOG_FILE = "operation_log.jsonl"


@dataclass
class OperationRecord:
    """単一操作の記録。"""
    operation_type: str           # "code_review" | "codebase_scan" | "improvement" | ...
    agent_name: str
    target: str = ""              # 対象ファイル・リポジトリなど
    tokens_used: int = 0
    success: bool = True
    duration_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OperationRecord":
        allowed = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in allowed})


@dataclass
class RepeatedPattern:
    """繰り返しが検出された操作パターン。"""
    pattern_key: str              # "operation_type:agent_name" or broader
    operation_type: str
    repeat_count: int
    total_tokens: int
    avg_tokens: float
    example_targets: List[str]
    first_seen: str
    last_seen: str
    flagged: bool = True
    gap_analysis_done: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OperationPatternDetector:
    """
    全エージェント実行をオペレーションログに記録し、
    繰り返しパターンを検出する。

    使い方:
        detector = OperationPatternDetector(repo_path)
        detector.record_operation("code_review", "CodeReviewAgent", tokens_used=4200)
        patterns = detector.detect_patterns()
    """

    REPEAT_THRESHOLD = 3  # 何回繰り返したら「パターン」とみなすか

    def __init__(self, repo_path: Optional[Path] = None, platform_home: Optional[Path] = None):
        if repo_path is not None:
            self._log_path = repo_path / ".repocorp" / OPERATION_LOG_FILE
        else:
            from core.platform.state import get_platform_home
            self._log_path = (platform_home or get_platform_home()) / OPERATION_LOG_FILE
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # 記録                                                                 #
    # ------------------------------------------------------------------ #

    def record_operation(
        self,
        operation_type: str,
        agent_name: str,
        target: str = "",
        tokens_used: int = 0,
        success: bool = True,
        duration_ms: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OperationRecord:
        """操作を記録してログに追記する。"""
        record = OperationRecord(
            operation_type=operation_type,
            agent_name=agent_name,
            target=target,
            tokens_used=tokens_used,
            success=success,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        return record

    # ------------------------------------------------------------------ #
    # 検出                                                                 #
    # ------------------------------------------------------------------ #

    def detect_patterns(self, min_repeat: Optional[int] = None) -> List[RepeatedPattern]:
        """
        ログを解析して繰り返しパターンを返す。
        min_repeat: デフォルトは REPEAT_THRESHOLD (3)
        """
        threshold = min_repeat or self.REPEAT_THRESHOLD
        records = self._load_records()

        # operation_type 単位でグループ化
        groups: Dict[str, List[OperationRecord]] = defaultdict(list)
        for rec in records:
            key = rec.operation_type
            groups[key].append(rec)

        patterns = []
        for op_type, recs in groups.items():
            if len(recs) < threshold:
                continue
            total_tokens = sum(r.tokens_used for r in recs)
            avg_tokens = total_tokens / len(recs) if recs else 0
            targets = list({r.target for r in recs if r.target})[:5]
            timestamps = sorted(r.timestamp for r in recs)
            patterns.append(RepeatedPattern(
                pattern_key=op_type,
                operation_type=op_type,
                repeat_count=len(recs),
                total_tokens=total_tokens,
                avg_tokens=avg_tokens,
                example_targets=targets,
                first_seen=timestamps[0],
                last_seen=timestamps[-1],
            ))

        # repeat_count 降順でソート
        patterns.sort(key=lambda p: p.repeat_count, reverse=True)
        return patterns

    def get_repeated_patterns(self) -> List[RepeatedPattern]:
        """繰り返しパターン（REPEAT_THRESHOLD以上）のみを返す。"""
        return [p for p in self.detect_patterns() if p.flagged]

    def get_all_records(self) -> List[OperationRecord]:
        return self._load_records()

    def get_summary(self) -> Dict[str, Any]:
        records = self._load_records()
        if not records:
            return {"total_operations": 0}
        counter = Counter(r.operation_type for r in records)
        total_tokens = sum(r.tokens_used for r in records)
        return {
            "total_operations": len(records),
            "total_tokens_used": total_tokens,
            "operation_counts": dict(counter.most_common()),
            "repeated_pattern_count": len(self.detect_patterns()),
        }

    # ------------------------------------------------------------------ #
    # 内部実装                                                             #
    # ------------------------------------------------------------------ #

    def _load_records(self) -> List[OperationRecord]:
        if not self._log_path.exists():
            return []
        records = []
        with open(self._log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(OperationRecord.from_dict(json.loads(line)))
                except Exception as e:
                    logger.debug("Failed to parse operation record: %s", e)
        return records
