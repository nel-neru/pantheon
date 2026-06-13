"""Tests for PlatformStateManager"""

import pytest

from core.org_factory import create_default_organization, create_organization_from_template
from core.platform.state import PlatformStateManager


@pytest.fixture
def tmp_psm(tmp_path):
    return PlatformStateManager(platform_home=tmp_path)


def test_not_initialized_by_default(tmp_psm):
    assert tmp_psm.is_initialized() is False


def test_initialize(tmp_psm):
    tmp_psm.initialize(meta_improvement_org_id="test-id")
    assert tmp_psm.is_initialized() is True
    cfg = tmp_psm.load_platform_config()
    assert cfg["meta_improvement_org_id"] == "test-id"


def test_save_and_load_organization(tmp_psm, tmp_path):
    # POSIX 絶対パスのハードコードは Windows の absolute 検証で load 時に弾かれる。
    # 意図は永続化の往復確認なので、プラットフォーム正規の絶対パスを使う。
    repo_path = str(tmp_path / "test-repo")
    org = create_default_organization("TestOrg", "テスト用")
    org.target_repo_path = repo_path
    tmp_psm.save_organization(org)

    loaded = tmp_psm.load_organizations()
    assert len(loaded) == 1
    assert loaded[0].name == "TestOrg"
    assert loaded[0].target_repo_path == repo_path


def test_load_organizations_warns_on_corrupt_file(tmp_psm, tmp_path, caplog):
    """壊れた JSON は耐性のためスキップするが、黙って消さず warning で観測可能にする。"""
    import logging

    org = create_default_organization("GoodOrg", "正常")
    tmp_psm.save_organization(org)
    (tmp_psm.orgs_dir / "broken.json").write_text("{not json", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="core.platform.state"):
        loaded = tmp_psm.load_organizations()
        tmp_psm.load_organizations()  # 2回目: 同一 path+mtime は WARNING を繰り返さない

    assert [o.name for o in loaded] == ["GoodOrg"]  # 正常分は読める
    warnings = [r for r in caplog.records if "broken.json" in r.message]
    assert len(warnings) == 1  # 破損は警告される（ただし洪水にならない＝初回のみ）
    assert (tmp_psm.orgs_dir / "broken.json").exists()  # ファイルは削除しない


def test_load_organization_by_name(tmp_psm):
    org = create_default_organization("SearchOrg", "検索テスト")
    tmp_psm.save_organization(org)
    found = tmp_psm.load_organization_by_name("SearchOrg")
    assert found is not None
    assert found.name == "SearchOrg"


def test_is_workspace_bound_reflects_repo(tmp_path):
    """1 ワークスペース = 1 Organization モデルの判定プロパティ。"""
    no_repo = create_default_organization("Unbound", "repo 無し")
    assert no_repo.is_workspace_bound is False

    bound = create_default_organization("Bound", "repo 付き", repo_path=str(tmp_path))
    assert bound.is_workspace_bound is True


def test_workspace_mode_org_is_managed_without_git(tmp_path):
    """Workspace モデル（§5）: git 無しでも data_location/is_managed で妥当に管理される。"""
    from core.models.organization import Organization

    org = Organization(
        name="WsCo",
        purpose="アプリ内データ管理の収益会社",
        management_mode="workspace",
        workspace_path=str(tmp_path / "ws"),
    )
    assert org.management_mode == "workspace"
    assert org.target_repo_path is None
    assert org.is_workspace_bound is False  # git repo は持たない
    assert org.is_managed is True
    assert org.data_location == str(tmp_path / "ws")


def test_get_org_state_manager_uses_workspace_path(tmp_psm, tmp_path):
    """workspace モード org の状態は workspace_path 配下で管理される。"""
    from core.models.organization import Organization

    ws = tmp_path / "wsdata"
    org = Organization(
        name="WsState", purpose="p", management_mode="workspace", workspace_path=str(ws)
    )
    sm = tmp_psm.get_org_state_manager(org)
    assert str(ws) in str(sm.state_dir)


def test_load_organization_by_name_not_found(tmp_psm):
    assert tmp_psm.load_organization_by_name("NonExistent") is None


def test_remove_organization(tmp_psm):
    org = create_default_organization("RemoveMe", "削除テスト")
    tmp_psm.save_organization(org)
    assert tmp_psm.remove_organization(str(org.id)) is True
    assert tmp_psm.load_organization_by_name("RemoveMe") is None


def test_remove_nonexistent_organization(tmp_psm):
    assert tmp_psm.remove_organization("nonexistent-id") is False


def test_get_org_state_manager_with_target_repo(tmp_psm, tmp_path):
    repo = tmp_path / "myapp"
    repo.mkdir()
    org = create_default_organization("AppOrg", "アプリ Org")
    org.target_repo_path = str(repo)
    sm = tmp_psm.get_org_state_manager(org)
    assert sm.state_dir == repo / ".pantheon"


def test_get_org_state_manager_no_target_repo(tmp_psm):
    org = create_default_organization("NoRepoOrg", "")
    sm = tmp_psm.get_org_state_manager(org)
    # フォールバック: platform_home 配下
    assert sm is not None


def test_save_shared_insight(tmp_psm):
    tmp_psm.save_shared_insight(
        "python活用", "List comprehension を使う", "TestOrg", tags=["python"]
    )
    insights = tmp_psm.get_shared_insights(tags=["python"])
    assert len(insights) == 1
    assert insights[0]["content"] == "List comprehension を使う"
    assert insights[0]["source_org"] == "TestOrg"


def test_multiple_organizations(tmp_psm):
    for i in range(3):
        org = create_default_organization(f"Org{i}", f"目的{i}")
        tmp_psm.save_organization(org)
    orgs = tmp_psm.load_organizations()
    assert len(orgs) == 3


def test_create_organization_from_template_sets_repo_path(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    org = create_organization_from_template("TemplatedOrg", "purpose", repo_path=repo)

    assert org.target_repo_path == str(repo)
