"""core/org_service（組織生成の単一経路）のテスト。"""

from __future__ import annotations

from core.org_service import create_org, normalize_isolation_level
from core.platform.state import PlatformStateManager


def _psm(tmp_path):
    return PlatformStateManager(platform_home=tmp_path)


def test_normalize_isolation_level():
    assert normalize_isolation_level("external") == "external"
    assert normalize_isolation_level("core") == "core"
    assert normalize_isolation_level("bogus") == "standard"
    assert normalize_isolation_level(None) == "standard"


def test_create_org_default_persists_standard(tmp_path):
    psm = _psm(tmp_path)
    org = create_org("Acme", "目的", target_repo_path=str(tmp_path / "repo"), psm=psm)
    assert org.isolation_level == "standard"
    # 永続化され、名前で引ける
    loaded = psm.load_organization_by_name("Acme")
    assert loaded is not None and loaded.id == org.id
    assert loaded.target_repo_path  # repo_path が設定される


def test_create_org_external_with_scope(tmp_path):
    psm = _psm(tmp_path)
    org = create_org(
        "Ext",
        isolation_level="external",
        allowed_path_scope=["content/", "knowledge/"],
        target_repo_path=str(tmp_path / "ws"),
        industry_genre="ai",
        persona_id="sns_growth_hacker",
        design_style="vibrant",
        psm=psm,
    )
    assert org.isolation_level == "external"
    assert org.allowed_path_scope == ["content/", "knowledge/"]
    assert org.industry_genre == "ai"
    assert org.persona_id == "sns_growth_hacker"
    assert org.design_style == "vibrant"


def test_create_org_invalid_isolation_coerced(tmp_path):
    org = create_org("X", isolation_level="garbage", persist=False)
    assert org.isolation_level == "standard"


def test_create_org_persist_false_not_saved(tmp_path):
    psm = _psm(tmp_path)
    create_org("Ghost", persist=False, psm=psm)
    assert psm.load_organization_by_name("Ghost") is None


def test_create_org_management_mode_and_workspace(tmp_path):
    org = create_org(
        "Ws",
        management_mode="workspace",
        workspace_path=str(tmp_path / "wsdata"),
        persist=False,
    )
    assert org.management_mode == "workspace"
    assert org.workspace_path == str(tmp_path / "wsdata")
