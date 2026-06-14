"""WS-2: Workspace 集計用 SQLite ミラー（計画 §5.2）。

JSON を**正準（source of truth）に保ったまま**、Organization 階層・収益・Playbook を
横断クエリ/集計できる **派生 SQLite ミラー**を提供する。SQLite は JSON から **毎回再構築**
できる読み取り専用ビューであり、ここに canonical データは持たない（消えても JSON から復元可能）。

設計方針（非破壊・低リスク）:
- 正準は引き続き ``PlatformStateManager``(JSON) / ``OutcomeStore``(JSON) / ``PlaybookStore``(JSON)。
- :meth:`WorkspaceDB.sync_from_canonical` はそれらを読み、全テーブルを **全消し→再投入**（冪等）。
  したがって移行リスク（部分書き込み・データ消失）が無い。
- 別ファイル（``~/.pantheon/workspace.db``）。提案ミラー（``query.db`` / sqlite_manager）とは独立。

§5.2 のテーブル群のうち、既存 canonical から導出できる中核を実装する:
``organizations`` / ``divisions`` / ``agents`` / ``revenue_records``(月次) / ``playbooks`` / ``meta``。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkspaceDB:
    """JSON 正準から再構築する Workspace 集計用 SQLite ミラー（読み取り専用ビュー）。"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS organizations (
                    id TEXT PRIMARY KEY, name TEXT, purpose TEXT, industry_genre TEXT,
                    management_mode TEXT, status TEXT, is_system INTEGER,
                    total_agents INTEGER, last_active TEXT
                );
                CREATE TABLE IF NOT EXISTS divisions (
                    id TEXT PRIMARY KEY, org_id TEXT, org_name TEXT, name TEXT, type TEXT
                );
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT, org_id TEXT, org_name TEXT, division_name TEXT,
                    name TEXT, skills TEXT
                );
                CREATE TABLE IF NOT EXISTS revenue_records (
                    org_name TEXT, month TEXT, amount REAL
                );
                CREATE TABLE IF NOT EXISTS playbooks (
                    entry_id TEXT PRIMARY KEY, title TEXT, category TEXT,
                    usefulness_score REAL, usage_count INTEGER, org_name TEXT
                );
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
                CREATE INDEX IF NOT EXISTS idx_div_org ON divisions(org_id);
                CREATE INDEX IF NOT EXISTS idx_rev_org ON revenue_records(org_name);
                """
            )

    def sync_from_canonical(self, *, platform_home: Path) -> Dict[str, int]:
        """JSON 正準（org/収益/playbook）から全テーブルを再構築する（全消し→再投入・冪等）。"""
        from core.metrics.outcomes import OutcomeStore
        from core.platform.state import PlatformStateManager

        psm = PlatformStateManager(platform_home)
        orgs = psm.load_organizations()
        store = OutcomeStore(platform_home=platform_home)

        org_rows: List[tuple] = []
        div_rows: List[tuple] = []
        agent_rows: List[tuple] = []
        rev_rows: List[tuple] = []
        for org in orgs:
            oid = str(org.id)
            org_rows.append(
                (
                    oid,
                    org.name,
                    org.purpose,
                    getattr(org, "industry_genre", ""),
                    org.management_mode,
                    org.status.value,
                    1 if org.is_system else 0,
                    len(org.get_all_agents()),
                    org.last_active.isoformat(),
                )
            )
            for div in org.divisions:
                div_rows.append((str(div.id), oid, org.name, div.name, div.type.value))
                for team in div.teams:
                    for agent in team.agents:
                        agent_rows.append(
                            (
                                str(agent.id),
                                oid,
                                org.name,
                                div.name,
                                agent.name,
                                ",".join(s.value for s in agent.skills),
                            )
                        )
            for month, amount in store.revenue_by_month(org.name).items():
                rev_rows.append((org.name, month, float(amount)))

        pb_rows: List[tuple] = []
        try:
            from core.intelligence.playbook import PlaybookStore

            for e in PlaybookStore(platform_home).list_entries():
                pb_rows.append(
                    (e.entry_id, e.title, e.category, e.usefulness_score, e.usage_count, e.org_name)
                )
        except Exception:  # noqa: BLE001 — playbook 不在でも org 同期は成立させる
            pass

        with self._conn:
            for table in ("organizations", "divisions", "agents", "revenue_records", "playbooks"):
                self._conn.execute(f"DELETE FROM {table}")  # noqa: S608 - 固定識別子
            self._conn.executemany("INSERT INTO organizations VALUES (?,?,?,?,?,?,?,?,?)", org_rows)
            self._conn.executemany("INSERT INTO divisions VALUES (?,?,?,?,?)", div_rows)
            self._conn.executemany("INSERT INTO agents VALUES (?,?,?,?,?,?)", agent_rows)
            self._conn.executemany("INSERT INTO revenue_records VALUES (?,?,?)", rev_rows)
            self._conn.executemany("INSERT INTO playbooks VALUES (?,?,?,?,?,?)", pb_rows)
            self._conn.execute(
                "INSERT INTO meta(key,value) VALUES('synced_at',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (_now_iso(),),
            )

        return {
            "organizations": len(org_rows),
            "divisions": len(div_rows),
            "agents": len(agent_rows),
            "revenue_records": len(rev_rows),
            "playbooks": len(pb_rows),
        }

    def stats(self) -> Dict[str, Any]:
        """各テーブルの件数＋最終同期時刻を返す（GUI/CLI の状態表示用）。"""
        out: Dict[str, Any] = {}
        with self._conn:
            for table in ("organizations", "divisions", "agents", "revenue_records", "playbooks"):
                row = self._conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()  # noqa: S608
                out[table] = int(row["n"]) if row else 0
            meta = self._conn.execute("SELECT value FROM meta WHERE key='synced_at'").fetchone()
            out["synced_at"] = meta["value"] if meta else None
        return out

    def revenue_by_org(self) -> List[Dict[str, Any]]:
        """org 別の累計収益（集計クエリの例・SQLite で横断集計できることの実証）。"""
        with self._conn:
            rows = self._conn.execute(
                "SELECT org_name, ROUND(SUM(amount),2) AS total "
                "FROM revenue_records GROUP BY org_name ORDER BY total DESC"
            ).fetchall()
        return [{"org_name": r["org_name"], "total_revenue": r["total"]} for r in rows]

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001
            pass


def _default_db_path(platform_home: Path) -> Path:
    return Path(platform_home) / "workspace.db"


def sync_workspace_db(*, platform_home=None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Workspace ミラーを JSON 正準から再構築し、件数サマリ＋DB パスを返す（CLI/API 用）。"""
    if platform_home is None:
        from core.platform.state import get_platform_home

        platform_home = get_platform_home()
    home = Path(platform_home)
    db = WorkspaceDB(db_path or _default_db_path(home))
    try:
        counts = db.sync_from_canonical(platform_home=home)
        return {"ok": True, "db_path": str(db.db_path), "counts": counts}
    finally:
        db.close()
