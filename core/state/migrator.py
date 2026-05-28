"""
StateMigrator — JSON→SQLite マイグレーション (G-02)
既存 .repocorp/{org_name}/ ディレクトリのJSONファイルをSQLiteに移行する。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from core.models.organization import ImprovementProposal
from core.state.sqlite_manager import SQLiteStateManager


@dataclass
class MigrationResult:
    migrated_proposals: int = 0
    migrated_decisions: int = 0
    errors: list[str] = field(default_factory=list)


class StateMigrator:
    """Migrates legacy JSON state files into SQLite storage."""

    def migrate(self, json_dir: Path, db_path: Path) -> MigrationResult:
        json_dir = Path(json_dir)
        manager = SQLiteStateManager(Path(db_path))
        result = MigrationResult()

        proposals_path = json_dir / "proposals.json"
        if proposals_path.exists():
            try:
                for item in self._load_items(proposals_path, "proposals"):
                    payload = dict(item)
                    payload.setdefault("review_id", str(uuid4()))
                    proposal = ImprovementProposal(**payload)
                    if manager.save_improvement_proposal(proposal):
                        result.migrated_proposals += 1
            except Exception as exc:
                result.errors.append(f"proposals.json: {exc}")

        decisions_path = json_dir / "decisions.json"
        if decisions_path.exists():
            try:
                for item in self._load_items(decisions_path, "decisions"):
                    payload = dict(item)
                    manager._save_decision_record(
                        decision_id=str(payload.get("id") or uuid4()),
                        action=str(payload.get("action") or payload.get("title") or "unknown"),
                        proposal_id=str(payload.get("proposal_id") or payload.get("id") or ""),
                        reason=str(payload.get("reason") or payload.get("content") or ""),
                        timestamp=str(payload.get("timestamp") or payload.get("created_at") or ""),
                    )
                    result.migrated_decisions += 1
            except Exception as exc:
                result.errors.append(f"decisions.json: {exc}")

        return result

    def _load_items(self, path: Path, list_key: str) -> list[dict]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        if isinstance(raw, dict):
            if isinstance(raw.get(list_key), list):
                return [item for item in raw[list_key] if isinstance(item, dict)]
            return [item for item in raw.values() if isinstance(item, dict)]
        return []
