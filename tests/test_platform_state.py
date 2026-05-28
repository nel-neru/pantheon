"""Tests for PlatformStateManager"""

import json
import tempfile
from pathlib import Path

import pytest

from core.platform.state import PlatformStateManager
from core.org_factory import create_default_organization


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


def test_save_and_load_organization(tmp_psm):
    org = create_default_organization("TestOrg", "テスト用")
    org.target_repo_path = "/tmp/test-repo"
    tmp_psm.save_organization(org)

    loaded = tmp_psm.load_organizations()
    assert len(loaded) == 1
    assert loaded[0].name == "TestOrg"
    assert loaded[0].target_repo_path == "/tmp/test-repo"


def test_load_organization_by_name(tmp_psm):
    org = create_default_organization("SearchOrg", "検索テスト")
    tmp_psm.save_organization(org)
    found = tmp_psm.load_organization_by_name("SearchOrg")
    assert found is not None
    assert found.name == "SearchOrg"


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
    assert sm.state_dir == repo / ".repocorp"


def test_get_org_state_manager_no_target_repo(tmp_psm):
    org = create_default_organization("NoRepoOrg", "")
    sm = tmp_psm.get_org_state_manager(org)
    # フォールバック: platform_home 配下
    assert sm is not None


def test_save_shared_insight(tmp_psm):
    tmp_psm.save_shared_insight("python活用", "List comprehension を使う", "TestOrg", tags=["python"])
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
