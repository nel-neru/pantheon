"""New Business Auto-Scaffolder（承認済み new_business 提案 → Organization+Business）の検証。

フライホイール actuate: トレンド由来の new_business 提案を 1 アクションで会社＋事業へ。
HITL は維持（提案は人手承認後に明示操作で呼ばれる前提）。決定論・LLM 非依存。
"""

from __future__ import annotations

from core.models.organization import DivisionType, OrganizationStatus
from core.orchestration.business_application import scaffold_business_from_proposal
from core.platform.business_store import BusinessStore
from core.platform.state import PlatformStateManager


def _proposal(divisions):
    return {
        "id": "prop-1",
        "category": "new_business",
        "title": "[新規会社候補] AIニュース解説",
        "intervention_spec": {
            "kind": "new_business",
            "name": "AIニュース解説社",
            "genre": "ai_news",
            "divisions": divisions,
        },
    }


def test_scaffold_creates_org_with_typed_divisions_and_business(tmp_path):
    psm = PlatformStateManager(platform_home=tmp_path)
    result = scaffold_business_from_proposal(
        _proposal(["audience_development", "monetization"]), psm=psm
    )
    assert result["ok"] and result["reused_org"] is False
    org = psm.load_organization_by_name("AIニュース解説社")
    assert org is not None
    assert org.isolation_level == "external" and org.management_mode == "workspace"
    assert org.status == OrganizationStatus.INCUBATING
    types = {d.type for d in org.divisions}
    assert DivisionType.AUDIENCE_DEVELOPMENT in types
    assert DivisionType.MONETIZATION in types
    # Business が member 1 社で作られる
    biz = BusinessStore(platform_home=tmp_path).get("AIニュース解説社")
    assert biz is not None and biz.member_orgs == ["AIニュース解説社"]


def test_scaffold_is_idempotent_on_rerun(tmp_path):
    psm = PlatformStateManager(platform_home=tmp_path)
    p = _proposal(["monetization"])
    scaffold_business_from_proposal(p, psm=psm)
    second = scaffold_business_from_proposal(p, psm=psm)
    assert second["reused_org"] is True
    # org も Business も重複しない
    assert len([o for o in psm.load_organizations() if o.name == "AIニュース解説社"]) == 1
    assert (
        len(
            [
                b
                for b in BusinessStore(platform_home=tmp_path).list_businesses()
                if b.name == "AIニュース解説社"
            ]
        )
        == 1
    )


def test_scaffold_rejects_non_new_business():
    import pytest

    with pytest.raises(ValueError):
        scaffold_business_from_proposal({"category": "content_asset"}, psm=None)


def test_cli_approve_scaffolds_new_business(tmp_path):
    """CLI 承認（cmd_proposal_apply）が new_business 提案を会社+事業へ組成する（Gap A 根治）。

    以前は file_path 無しの new_business が「meta-level 提案」として承認前に棄却され、
    Web（POST /api/businesses/from-proposal）からしか事業化できなかった。PolicyEngine は
    is_meta carve-out で通過させ（REJECT でなく HUMAN_REQUIRED）、専用 executor に委任する。
    """
    import asyncio
    from types import SimpleNamespace
    from uuid import uuid4

    from commands.org import cmd_proposal_apply
    from core.models.organization import ImprovementProposal
    from core.org_factory import create_default_organization

    psm = PlatformStateManager(platform_home=tmp_path)
    hq = create_default_organization("HQ", "本社")
    psm.save_organization(hq)
    sm = psm.get_org_state_manager(hq)
    prop = ImprovementProposal(
        review_id=uuid4(),
        title="[新規会社候補] AI動画解説",
        description="d",
        category="new_business",
        status="proposed",
        is_meta=True,
        target_kind="org_structure",
        intervention_spec={
            "kind": "new_business",
            "name": "AI動画解説社",
            "genre": "ai_video",
            "divisions": ["audience_development", "monetization"],
        },
    )
    sm.save_improvement_proposal(prop)

    args = SimpleNamespace(
        org_name="HQ",
        proposal_id=str(prop.id)[:8],
        yes=True,
        github_token=None,
        github_repo=None,
    )
    asyncio.run(
        cmd_proposal_apply(
            args,
            confirm_action=lambda *a, **k: True,
            get_orchestrator=lambda: None,  # new_business 経路では使わない
            get_psm=lambda: psm,
            require_api_key=lambda *a, **k: None,  # 同上（LLM 非依存）
        )
    )

    # 会社 + 事業が立ち上がる（CLI 承認から到達できる）
    assert psm.load_organization_by_name("AI動画解説社") is not None
    biz = BusinessStore(platform_home=tmp_path).get("AI動画解説社")
    assert biz is not None and biz.member_orgs == ["AI動画解説社"]
    # 提案は done に遷移（再棄却されない）
    done = [p for p in sm.get_all_improvement_proposals() if str(p["id"]) == str(prop.id)]
    assert done and done[0]["status"] == "done"


def test_from_proposal_api_end_to_end(tmp_path, monkeypatch):
    """承認済み提案 → POST /api/businesses/from-proposal で組成し提案を done にする。"""
    from uuid import uuid4

    from fastapi.testclient import TestClient

    import web.server as server
    from core.models.organization import ImprovementProposal

    psm = PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)
    from core.org_factory import create_default_organization

    hq = create_default_organization("HQ", "本社")
    psm.save_organization(hq)
    sm = psm.get_org_state_manager(hq)
    prop = ImprovementProposal(
        review_id=uuid4(),
        title="[新規会社候補] ニッチ動画",
        description="d",
        category="new_business",
        status="proposed",
        is_meta=True,
        target_kind="org_structure",
        intervention_spec={
            "kind": "new_business",
            "name": "ニッチ動画社",
            "genre": "video",
            "divisions": ["audience_development", "content_production", "monetization"],
        },
    )
    sm.save_improvement_proposal(prop)

    client = TestClient(server.app)
    resp = client.post(
        "/api/businesses/from-proposal",
        json={"org_name": "HQ", "proposal_id": str(prop.id)[:8]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] and body["org_name"] == "ニッチ動画社"
    assert psm.load_organization_by_name("ニッチ動画社") is not None
    # 提案は done に遷移
    done = [p for p in sm.get_all_improvement_proposals() if str(p["id"]) == str(prop.id)]
    assert done and done[0]["status"] == "done"
    # 未知提案は 404
    assert (
        client.post(
            "/api/businesses/from-proposal", json={"org_name": "HQ", "proposal_id": "nope999"}
        ).status_code
        == 404
    )
