"""
CapabilityHistoryTracker — 能力進化追跡 (L-08)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.platform.state import get_platform_home


@dataclass
class CapabilityAddition:
    capability_id: str
    capability_name: str
    capability_type: str
    reason: str
    gap_description: str
    added_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_dict(cls, d: dict) -> "CapabilityAddition":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class CapabilityHistoryTracker:
    """Append-only capability history tracker."""

    def __init__(self, platform_home=None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.file_path = self.platform_home / "capability_history.jsonl"

    def record_addition(self, name: str, ctype: str, reason: str, gap: str) -> CapabilityAddition:
        addition = CapabilityAddition(
            capability_id=f"cap:{uuid4().hex[:8]}",
            capability_name=name,
            capability_type=ctype,
            reason=reason,
            gap_description=gap,
        )
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with self.file_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(addition), ensure_ascii=False) + "\n")
        return addition

    def get_history(self, limit: int = 20) -> list[CapabilityAddition]:
        if not self.file_path.exists():
            return []
        lines = [
            line for line in self.file_path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        out: list[CapabilityAddition] = []
        for line in lines[-limit:]:
            try:
                out.append(CapabilityAddition.from_dict(json.loads(line)))
            except Exception:  # 破損行/スキーマ進化レコードはスキップ
                continue
        return out

    def format_timeline(self) -> str:
        history = self.get_history(limit=100)
        if not history:
            return "能力追加履歴はありません。"
        lines = ["Capability Timeline"]
        for item in history:
            lines.append(
                f"- {item.added_at[:19]} | {item.capability_name} ({item.capability_type}) | {item.reason}"
            )
        return "\n".join(lines)
