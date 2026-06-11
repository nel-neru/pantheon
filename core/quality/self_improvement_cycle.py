"""
SelfImprovementCycle — 真の自己改善フルサイクル (H-08~H-10)

Meta-Improvement Org → Core改善提案 → Human承認 → 適用 → 次の分析
のフルサイクルを管理する。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.platform.state import get_platform_home
from core.quality.meta_improvement_analyzer import MetaImprovementAnalyzer
from core.quality.prompt_evolution_engine import PromptEvolutionEngine


@dataclass
class CoreVersion:
    version: str
    improved_at: str
    changes: list[str] = field(default_factory=list)


@dataclass
class SelfImprovementRecord:
    cycle_id: str
    improvements: list[str]
    meta_proposals_count: int
    applied_count: int
    version_before: str
    version_after: str
    started_at: str
    completed_at: str


class SelfImprovementCycle:
    """Coordinates the human-approved core self-improvement feedback loop."""

    def __init__(self, platform_home: Path = None, meta_analyzer=None, prompt_engine=None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.version_file = self.platform_home / "core_version.json"
        self.history_file = self.platform_home / "core_improvement_history.jsonl"
        self.meta_analyzer = meta_analyzer or MetaImprovementAnalyzer()
        self.prompt_engine = prompt_engine or PromptEvolutionEngine(self.platform_home)

    def get_current_version(self) -> CoreVersion:
        if not self.version_file.exists():
            return CoreVersion(version="1.0.0", improved_at="", changes=[])
        payload = json.loads(self.version_file.read_text(encoding="utf-8"))
        return CoreVersion(
            version=payload.get("version", "1.0.0"),
            improved_at=payload.get("improved_at", ""),
            changes=list(payload.get("changes", [])),
        )

    def run_meta_analysis_cycle(self, repo_root: Path) -> SelfImprovementRecord:
        started_at = datetime.now(timezone.utc).isoformat()
        analysis = self.meta_analyzer.analyze_architecture(Path(repo_root))
        proposals = self.meta_analyzer.generate_meta_proposals(analysis)
        current_version = self.get_current_version()
        next_version = self._increment_version(current_version.version)
        completed_at = datetime.now(timezone.utc).isoformat()
        improvements = [proposal.title for proposal in proposals]
        cycle_id = f"cycle:{started_at.replace(':', '').replace('-', '').replace('.', '')}"
        record = SelfImprovementRecord(
            cycle_id=cycle_id,
            improvements=improvements,
            meta_proposals_count=len(proposals),
            applied_count=0,
            version_before=current_version.version,
            version_after=next_version,
            started_at=started_at,
            completed_at=completed_at,
        )
        version = CoreVersion(
            version=next_version,
            improved_at=completed_at,
            changes=[
                f"HUMAN_REQUIRED: {len(proposals)} proposal(s) awaiting approval",
                *improvements,
            ],
        )
        self.version_file.write_text(
            json.dumps(asdict(version), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with self.history_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        return record

    def get_improvement_history(self, limit: int = 10) -> list[SelfImprovementRecord]:
        if not self.history_file.exists():
            return []
        records: list[SelfImprovementRecord] = []
        for line in self.history_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            records.append(SelfImprovementRecord(**json.loads(line)))
        return records[-limit:]

    def _increment_version(self, version: str) -> str:
        parts = version.split(".")
        if len(parts) != 3:
            return version
        major, minor, patch = parts
        try:
            next_patch = int(patch) + 1
        except ValueError:
            return version
        return f"{major}.{minor}.{next_patch}"
