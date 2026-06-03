"""F2: e2e（提案 → 承認 → 適用/PR）統合テスト。

goal→proposal は `tests/test_e2e.py`、検証済み変更の受け渡しは
`tests/test_core_improve_approval.py` がカバーする。本ファイルは実 PlatformStateManager 上で
サーバの承認エンドポイントが提案を実行へ流し、成功時に PR/branch を返して done に、
失敗時に failed にすることを固定する（git/LLM は FakeOrchestrator で差し替え）。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

import agents.orchestrator_agent as orchestrator_module
import web.server as server
from core.models.organization import ImprovementProposal
from core.org_factory import create_default_organization

client = TestClient(server.app)


def _setup_proposal(tmp_path, monkeypatch, *, category="performance", file_path="core/sample.py"):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)
    server._invalidate_proposals_cache()

    org = create_default_organization("AcmeApp", "improve acme")
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)
    proposal = ImprovementProposal(
        review_id=uuid4(),
        priority="medium",
        category=category,
        title="性能改善: N+1 解消",
        description="...",
        file_path=file_path,
        expected_impact="faster",
        implementation_difficulty="medium",
        status="proposed",
    )
    sm.save_improvement_proposal(proposal)
    return org, sm, proposal


def _read_status(sm, proposal_id) -> str:
    path = sm.state_dir / "improvements" / f"{proposal_id}.json"
    return str(json.loads(path.read_text(encoding="utf-8")).get("status"))


def _patch_orchestrator(monkeypatch, result):
    class _FakeOrchestrator:
        async def run(self, task):
            return result

    monkeypatch.setattr(
        orchestrator_module.OrchestratorAgent,
        "create",
        classmethod(lambda cls, llm_client=None, **kwargs: _FakeOrchestrator()),
    )


def test_approve_applies_and_returns_pr_url(tmp_path, monkeypatch):
    org, sm, proposal = _setup_proposal(tmp_path, monkeypatch)
    _patch_orchestrator(
        monkeypatch,
        SimpleNamespace(
            success=True,
            output={
                "branch": "repocorp/improvement-n1",
                "pr_url": "https://github.com/acme/app/pull/42",
                "change_summary": "removed N+1",
            },
            error=None,
        ),
    )

    resp = client.post(f"/api/proposals/{org.name}/{proposal.id}/approve", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "done"
    assert body["pr_url"] == "https://github.com/acme/app/pull/42"
    assert body["branch"] == "repocorp/improvement-n1"

    # 永続化されたステータスも done
    assert _read_status(sm, proposal.id) == "done"


def test_approve_execution_failure_marks_failed(tmp_path, monkeypatch):
    org, sm, proposal = _setup_proposal(tmp_path, monkeypatch)
    _patch_orchestrator(
        monkeypatch,
        SimpleNamespace(success=False, output={}, error="apply failed: conflict"),
    )

    resp = client.post(f"/api/proposals/{org.name}/{proposal.id}/approve", json={})
    assert resp.status_code == 500
    assert _read_status(sm, proposal.id) == "failed"


def test_approve_rejects_proposal_without_file_path(tmp_path, monkeypatch):
    org, sm, proposal = _setup_proposal(tmp_path, monkeypatch, file_path="")
    resp = client.post(f"/api/proposals/{org.name}/{proposal.id}/approve", json={})
    assert resp.status_code == 400
