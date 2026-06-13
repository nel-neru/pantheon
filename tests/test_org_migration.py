"""WS-1: repo→workspace 移行コア（core/orchestration/org_migration.py）のテスト。

純粋なモデル変換／パス決定のみを検証する（git 操作・実データ移動は対象外）。
Organization を直接生成し、tmp_path を workspace_root として注入する。
"""

from __future__ import annotations

from pathlib import Path

from core.models.organization import Organization
from core.orchestration.org_migration import (
    migrate_repo_org_to_workspace,
    plan_repo_to_workspace_migration,
)


def _repo_org(name: str = "Revenue Org", repo: str = "/tmp/revenue-repo") -> Organization:
    """repo モードの Organization を生成する（target_repo_path は絶対パス必須）。"""
    return Organization(
        name=name,
        purpose="売上を伸ばす",
        target_repo_path=str(Path(repo).absolute()),
    )


# ------------------------------------------------------------------
# plan_repo_to_workspace_migration
# ------------------------------------------------------------------


def test_plan_repo_org_returns_target_workspace(tmp_path: Path) -> None:
    org = _repo_org(name="MyOrg")
    plan = plan_repo_to_workspace_migration(org, workspace_root=tmp_path)

    assert plan["already_workspace"] is False
    assert plan["org_name"] == "MyOrg"
    assert plan["from_repo"] == org.target_repo_path
    # 移行先は workspace_root / safe(name)。
    assert plan["to_workspace"] == str((tmp_path / "MyOrg").absolute())


def test_plan_does_not_mutate_org(tmp_path: Path) -> None:
    org = _repo_org()
    before_mode = org.management_mode
    before_ws = org.workspace_path

    plan_repo_to_workspace_migration(org, workspace_root=tmp_path)

    # plan は副作用なし（モデル不変）。
    assert org.management_mode == before_mode == "repo"
    assert org.workspace_path == before_ws is None


def test_plan_already_workspace_is_idempotent(tmp_path: Path) -> None:
    ws = str((tmp_path / "existing").absolute())
    org = Organization(
        name="WsOrg",
        purpose="既に workspace",
        management_mode="workspace",
        workspace_path=ws,
    )
    plan = plan_repo_to_workspace_migration(org, workspace_root=tmp_path)

    assert plan["already_workspace"] is True
    assert plan["org_name"] == "WsOrg"
    assert plan["to_workspace"] == ws


# ------------------------------------------------------------------
# migrate_repo_org_to_workspace
# ------------------------------------------------------------------


def test_migrate_sets_workspace_mode_and_path(tmp_path: Path) -> None:
    org = _repo_org(name="MyOrg")
    repo_before = org.target_repo_path

    migrated = migrate_repo_org_to_workspace(org, workspace_root=tmp_path)

    assert migrated.management_mode == "workspace"
    assert migrated.workspace_path == str((tmp_path / "MyOrg").absolute())
    # target_repo_path は履歴／移行元として保持される。
    assert migrated.target_repo_path == repo_before


def test_migrate_data_location_points_to_workspace(tmp_path: Path) -> None:
    org = _repo_org()
    migrated = migrate_repo_org_to_workspace(org, workspace_root=tmp_path)

    # data_location は workspace モードでは workspace_path を指す。
    assert migrated.data_location == migrated.workspace_path
    assert migrated.data_location == str((tmp_path / "Revenue-Org").absolute())
    assert migrated.is_managed is True


def test_migrate_workspace_path_is_absolute(tmp_path: Path) -> None:
    org = _repo_org()
    migrated = migrate_repo_org_to_workspace(org, workspace_root=tmp_path)

    assert Path(migrated.workspace_path).is_absolute()


def test_migrate_already_workspace_is_idempotent(tmp_path: Path) -> None:
    ws = str((tmp_path / "existing").absolute())
    org = Organization(
        name="WsOrg",
        purpose="既に workspace",
        management_mode="workspace",
        workspace_path=ws,
    )

    result = migrate_repo_org_to_workspace(org, workspace_root=tmp_path)

    # 既に workspace なら no-op（同一オブジェクト・パス不変）。
    assert result is org
    assert result.management_mode == "workspace"
    assert result.workspace_path == ws


def test_migrate_is_idempotent_when_applied_twice(tmp_path: Path) -> None:
    org = _repo_org(name="Idem")
    once = migrate_repo_org_to_workspace(org, workspace_root=tmp_path)
    ws_after_first = once.workspace_path

    twice = migrate_repo_org_to_workspace(once, workspace_root=tmp_path)

    assert twice.management_mode == "workspace"
    assert twice.workspace_path == ws_after_first


# ------------------------------------------------------------------
# safe 化
# ------------------------------------------------------------------


def test_safe_name_replaces_unsafe_chars(tmp_path: Path) -> None:
    org = _repo_org(name="Foo Bar/Baz:Qux")
    migrated = migrate_repo_org_to_workspace(org, workspace_root=tmp_path)

    # 英数_- 以外（空白 / : 等）は "-" に置換される。
    assert migrated.workspace_path == str((tmp_path / "Foo-Bar-Baz-Qux").absolute())


def test_safe_name_keeps_word_underscore_hyphen(tmp_path: Path) -> None:
    org = _repo_org(name="my_org-01")
    plan = plan_repo_to_workspace_migration(org, workspace_root=tmp_path)

    # 許可文字（英数 / _ / -）はそのまま保持される。
    assert plan["to_workspace"] == str((tmp_path / "my_org-01").absolute())


# ------------------------------------------------------------------
# CLI 配線（cmd_org_migrate_workspace）
# ------------------------------------------------------------------


def test_cli_migrate_to_workspace(tmp_path: Path) -> None:
    """CLI 経由で repo 組織を workspace モードへ移行・保存する（WS-1 配線）。"""
    import argparse
    import asyncio

    from commands.org import cmd_org_migrate_workspace
    from core.org_factory import create_default_organization
    from core.platform.state import PlatformStateManager

    home = tmp_path / "home"
    psm = PlatformStateManager(platform_home=home)
    repo = tmp_path / "repo"
    repo.mkdir()
    psm.save_organization(create_default_organization("Mig Co", "売上", repo_path=str(repo)))

    args = argparse.Namespace(name="Mig Co", dry_run=False)
    asyncio.run(cmd_org_migrate_workspace(args, get_psm=lambda: psm))

    reloaded = psm.load_organization_by_name("Mig Co")
    assert reloaded.management_mode == "workspace"
    assert reloaded.workspace_path is not None


def test_cli_migrate_dry_run_does_not_mutate(tmp_path: Path) -> None:
    """--dry-run は計画表示のみでモデルを変更しない。"""
    import argparse
    import asyncio

    from commands.org import cmd_org_migrate_workspace
    from core.org_factory import create_default_organization
    from core.platform.state import PlatformStateManager

    home = tmp_path / "home"
    psm = PlatformStateManager(platform_home=home)
    repo = tmp_path / "repo"
    repo.mkdir()
    psm.save_organization(create_default_organization("Dry Co", "売上", repo_path=str(repo)))

    args = argparse.Namespace(name="Dry Co", dry_run=True)
    asyncio.run(cmd_org_migrate_workspace(args, get_psm=lambda: psm))

    reloaded = psm.load_organization_by_name("Dry Co")
    assert reloaded.management_mode == "repo"  # 変更されていない
