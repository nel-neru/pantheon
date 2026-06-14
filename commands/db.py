"""`pantheon db` — Workspace 集計用 SQLite ミラー（WS-2 / §5.2）。

`sync` で JSON 正準（組織/収益/Playbook）から SQLite ミラーを再構築し、`stats` で件数を表示する。
SQLite は派生・読み取り専用ビュー（JSON が正準）。いつでも `sync` で作り直せる。
"""

from __future__ import annotations

import argparse
from typing import Any


async def cmd_db_sync(args: argparse.Namespace) -> None:
    """JSON 正準から Workspace 集計 SQLite ミラーを再構築する。"""
    from core.state.workspace_db import sync_workspace_db

    result = sync_workspace_db()
    counts = result["counts"]
    print(f"[db] Workspace ミラーを再構築: {result['db_path']}")
    print(
        f"  organizations={counts['organizations']} divisions={counts['divisions']} "
        f"agents={counts['agents']} revenue_records={counts['revenue_records']} "
        f"playbooks={counts['playbooks']}"
    )


async def cmd_db_stats(args: argparse.Namespace) -> None:
    """Workspace ミラーの件数・最終同期時刻を表示する。"""
    from pathlib import Path

    from core.platform.state import get_platform_home
    from core.state.workspace_db import WorkspaceDB, _default_db_path

    db = WorkspaceDB(_default_db_path(Path(get_platform_home())))
    try:
        st = db.stats()
    finally:
        db.close()
    if st.get("synced_at") is None:
        print("[db] 未同期です（pantheon db sync で作成）")
        return
    print(f"[db] 最終同期: {st['synced_at']}")
    for key in ("organizations", "divisions", "agents", "revenue_records", "playbooks"):
        print(f"  {key}={st[key]}")


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("db", help="Workspace 集計 SQLite ミラー（WS-2）")
    sub = parser.add_subparsers(dest="db_command", required=True)

    sp = sub.add_parser("sync", help="JSON 正準から SQLite ミラーを再構築")
    sp.set_defaults(handler_name="cmd_db_sync")

    sp = sub.add_parser("stats", help="ミラーの件数・最終同期時刻を表示")
    sp.set_defaults(handler_name="cmd_db_stats")
