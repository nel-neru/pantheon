"""
SQLiteStateManager — SQLite状態管理 (G-01~G-03)

既存JSONファイル依存をSQLiteに移行し、
並行アクセス安全性・検索性・トランザクション保証を提供する。
既存のRepoStateManagerと同一インターフェースを持つ。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.models.organization import ACTIVE_IMPROVEMENT_PROPOSAL_STATUSES, ImprovementProposal


class SQLiteStateManager:
    """SQLite-backed state manager for improvement proposals and decisions.

    注意: これは **副（secondary）クエリ用ミラー** であり source of truth ではない。
    ImprovementProposal の正準ストアは `core.state.manager.RepoStateManager`（各リポジトリ内 JSON）。
    この SQLite ストアは `StateMigrator` 経由でオンデマンドに投入され、`pantheon query --db-path`
    で読まれるだけで、analyze / approve / reject / apply からは書き込まれない。
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT PRIMARY KEY,
                    review_id TEXT,
                    priority TEXT,
                    category TEXT,
                    title TEXT,
                    description TEXT,
                    file_path TEXT,
                    status TEXT,
                    created_at TEXT,
                    data TEXT
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    action TEXT,
                    proposal_id TEXT,
                    reason TEXT,
                    timestamp TEXT
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS insights (
                    id TEXT PRIMARY KEY,
                    key TEXT,
                    value TEXT,
                    updated_at TEXT
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_proposals_status_created ON proposals(status, created_at DESC)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decisions(timestamp DESC)"
            )

    def save_improvement_proposal(self, proposal: ImprovementProposal) -> bool:
        payload = proposal.model_dump(mode="json")
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO proposals (
                    id, review_id, priority, category, title, description,
                    file_path, status, created_at, data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(proposal.id),
                    str(proposal.review_id),
                    proposal.priority,
                    proposal.category,
                    proposal.title,
                    proposal.description,
                    proposal.file_path,
                    proposal.status,
                    proposal.created_at.isoformat(),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
        return True

    def get_pending_improvement_proposals(self, limit: int = 50) -> list[ImprovementProposal]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT data FROM proposals
                WHERE status IN (?, ?, ?)
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (*ACTIVE_IMPROVEMENT_PROPOSAL_STATUSES, limit),
            ).fetchall()
        proposals: list[ImprovementProposal] = []
        for row in rows:
            try:
                data = json.loads(row["data"])
                if not data.get("review_id"):
                    data["review_id"] = str(uuid4())
                proposals.append(ImprovementProposal(**data))
            except Exception:
                continue
        return proposals

    def get_pending_proposals(self, limit: int = 50) -> list[ImprovementProposal]:
        return self.get_pending_improvement_proposals(limit=limit)

    def save_proposal(self, proposal: ImprovementProposal) -> bool:
        return self.save_improvement_proposal(proposal)

    def update_proposal_status(self, proposal_id: str, status: str) -> bool:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, data FROM proposals WHERE id LIKE ? || '%'",
                (proposal_id,),
            ).fetchall()
            if not rows:
                return False

            updated_at = datetime.now(timezone.utc).isoformat()
            with self._conn:
                for row in rows:
                    data = json.loads(row["data"])
                    data["status"] = status
                    data["last_updated"] = updated_at
                    self._conn.execute(
                        "UPDATE proposals SET status = ?, data = ? WHERE id = ?",
                        (status, json.dumps(data, ensure_ascii=False), row["id"]),
                    )
        return True

    def record_decision(self, action: str, proposal_id: str, reason: str = "") -> None:
        self._save_decision_record(
            decision_id=str(uuid4()),
            action=action,
            proposal_id=proposal_id,
            reason=reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def get_recent_decisions(self, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, action, proposal_id, reason, timestamp FROM decisions ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def query_proposals(
        self,
        sql_filter: str = "",
        limit: int = 50,
        field_filters: dict[str, str] | None = None,
    ) -> list[dict]:
        safe_limit = max(1, min(int(limit), 500))
        if field_filters:
            allowed_fields = {"id", "priority", "category", "title", "file_path", "status"}
            unknown_fields = set(field_filters) - allowed_fields
            if unknown_fields:
                raise ValueError(f"Unsupported filter fields: {', '.join(sorted(unknown_fields))}")

            where_clause = " AND ".join(f"{field} = ?" for field in field_filters)
            query = f"SELECT * FROM proposals WHERE {where_clause} LIMIT ?"
            params = (*field_filters.values(), safe_limit)
            with self._lock:
                rows = self._conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

        filter_clause = (sql_filter or "").strip()
        if filter_clause:
            upper = filter_clause.upper()
            forbidden = (
                "INSERT",
                "UPDATE",
                "DELETE",
                "DROP",
                "ALTER",
                "CREATE",
                "ATTACH",
                "DETACH",
                "PRAGMA",
                ";",
                "--",
                "/*",
            )
            if any(token in upper for token in forbidden):
                raise ValueError("Unsafe SQL filter.")
            if not (upper.startswith("WHERE ") or upper.startswith("ORDER BY ")):
                raise ValueError("Only WHERE/ORDER BY filters are allowed.")

        query = f"SELECT * FROM proposals {filter_clause} LIMIT ?"
        with self._lock:
            rows = self._conn.execute(query, (safe_limit,)).fetchall()
        return [dict(row) for row in rows]

    def _save_decision_record(
        self,
        decision_id: str,
        action: str,
        proposal_id: str,
        reason: str,
        timestamp: str,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO decisions (id, action, proposal_id, reason, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (decision_id, action, proposal_id, reason, timestamp),
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __del__(self) -> None:
        try:
            with self._lock:
                self._conn.close()
        except Exception:
            pass
