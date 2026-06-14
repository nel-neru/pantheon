"""WS-2: Workspace 集計 SQLite ミラー（core/state/workspace_db）のテスト。

JSON 正準から再構築する派生ビュー。非破壊（JSON は触らない）・冪等（再 sync で重複しない）を検証する。
"""

from __future__ import annotations

from core.metrics.outcomes import OutcomeStore
from core.org_factory import create_default_organization
from core.platform.state import PlatformStateManager
from core.state.workspace_db import WorkspaceDB, sync_workspace_db


def _setup(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: home)
    psm = PlatformStateManager(platform_home=home)
    psm.save_organization(create_default_organization("Reachy", "集客"))
    store = OutcomeStore(platform_home=home)
    store.record("Reachy", "revenue", 1000, occurred_at="2026-05-10")
    store.record("Reachy", "revenue", 1500, occurred_at="2026-06-10")
    return home, psm


def test_sync_builds_mirror_from_canonical(tmp_path, monkeypatch):
    home, _psm = _setup(tmp_path, monkeypatch)
    result = sync_workspace_db(platform_home=home)

    assert result["ok"] is True
    counts = result["counts"]
    assert counts["organizations"] == 1
    assert counts["divisions"] >= 1
    assert counts["agents"] >= 1
    assert counts["revenue_records"] == 2  # 2026-05, 2026-06
    # JSON 正準は触らない（org JSON は残る）
    assert _psm.load_organization_by_name("Reachy") is not None


def test_sync_is_idempotent_full_rebuild(tmp_path, monkeypatch):
    """再 sync しても全消し→再投入で件数が二重化しない。"""
    home, _ = _setup(tmp_path, monkeypatch)
    first = sync_workspace_db(platform_home=home)
    second = sync_workspace_db(platform_home=home)
    assert first["counts"] == second["counts"]  # 冪等


def test_stats_and_revenue_by_org_aggregate(tmp_path, monkeypatch):
    home, _ = _setup(tmp_path, monkeypatch)
    sync_workspace_db(platform_home=home)

    from core.state.workspace_db import _default_db_path

    db = WorkspaceDB(_default_db_path(home))
    try:
        stats = db.stats()
        assert stats["organizations"] == 1
        assert stats["synced_at"] is not None
        # SQLite 横断集計が効く（org 別累計収益）
        rev = db.revenue_by_org()
        assert {"org_name": "Reachy", "total_revenue": 2500.0} in rev
    finally:
        db.close()


def test_sync_empty_platform_is_safe(tmp_path, monkeypatch):
    """org も収益も無い状態でも sync は壊れず 0 件で完了する。"""
    home = tmp_path / "home"
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: home)
    PlatformStateManager(platform_home=home)
    result = sync_workspace_db(platform_home=home)
    assert result["ok"] is True
    assert result["counts"]["organizations"] == 0
