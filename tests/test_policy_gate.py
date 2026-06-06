"""
Phase 0 — 信頼と安全: Web の承認/却下は必ず PolicyEngine を通り、github_repo が executor に渡る。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

import web.server as server
from core.models.organization import ImprovementProposal
from core.org_factory import create_default_organization

client = TestClient(server.app)


def _capturing_orchestrator(captured: dict):
    class FakeOrchestrator:
        async def run(self, task):
            captured["input"] = dict(task.input)
            return SimpleNamespace(
                success=True,
                output={"change_summary": "ok", "branch": "b", "pr_url": "u"},
                error=None,
            )

    return FakeOrchestrator()


def test_approve_blocks_proposal_rejected_by_policy(tmp_path, monkeypatch):
    """file_path の無い meta-level 提案は DEFAULT_POLICY の auto_reject で 409 になる。"""
    psm = server.PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("PolicyOrg", "policy gate")
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)
    proposal = ImprovementProposal(
        review_id=uuid4(),
        title="meta proposal",
        description="no file path",
        priority="low",
        category="meta",
        file_path="",
    )
    sm.save_improvement_proposal(proposal)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    response = client.post(f"/api/proposals/{org.name}/{str(proposal.id)[:8]}/approve")
    assert response.status_code == 409
    assert "ポリシー" in response.json()["detail"]


def test_approve_passes_github_repo_to_executor(tmp_path, monkeypatch):
    import agents.orchestrator_agent as orchestrator_module

    psm = server.PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("RepoOrg", "github repo passthrough")
    org.target_repo_path = str(tmp_path / "repo")
    org.github_repo = "acme/widgets"
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)
    proposal = ImprovementProposal(
        review_id=uuid4(),
        title="fix",
        description="d",
        priority="low",
        category="documentation",
        file_path="docs/x.md",
    )
    sm.save_improvement_proposal(proposal)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    captured: dict = {}
    monkeypatch.setattr(
        orchestrator_module.OrchestratorAgent,
        "create",
        classmethod(lambda cls, llm_client=None, **kwargs: _capturing_orchestrator(captured)),
    )

    response = client.post(f"/api/proposals/{org.name}/{str(proposal.id)[:8]}/approve")
    assert response.status_code == 200
    assert captured["input"]["github_repo"] == "acme/widgets"
    # 自動承認カテゴリ(documentation/low)なので policy は auto_approve
    assert response.json()["policy"]["decision"] == "auto_approve"


def test_resolve_github_repo_priority(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    # 1. Organization.github_repo を最優先
    org = SimpleNamespace(github_repo="owner/explicit")
    assert server._resolve_github_repo(org, tmp_path) == "owner/explicit"
    # 2. 無ければ環境変数
    org2 = SimpleNamespace(github_repo=None)
    monkeypatch.setenv("GITHUB_REPO", "owner/fromenv")
    assert server._resolve_github_repo(org2, tmp_path) == "owner/fromenv"


def test_shared_repo_resolver_priority(tmp_path, monkeypatch):
    from github_integration import repo_resolver

    monkeypatch.delenv("GITHUB_REPO", raising=False)
    # 明示指定が最優先
    assert (
        repo_resolver.resolve_github_repo(
            "cli/explicit", SimpleNamespace(github_repo="o/r"), tmp_path
        )
        == "cli/explicit"
    )
    # 次に Organization.github_repo
    assert (
        repo_resolver.resolve_github_repo(None, SimpleNamespace(github_repo="o/r"), tmp_path)
        == "o/r"
    )
    # 次に環境変数
    monkeypatch.setenv("GITHUB_REPO", "o/env")
    assert (
        repo_resolver.resolve_github_repo(None, SimpleNamespace(github_repo=None), tmp_path)
        == "o/env"
    )


def test_git_remote_github_repo_parses_https_and_ssh(tmp_path, monkeypatch):
    def fake_run(cmd, **kwargs):
        return SimpleNamespace(stdout="git@github.com:acme/widgets.git\n", stderr="", returncode=0)

    monkeypatch.setattr(server.subprocess, "run", fake_run)
    assert server._git_remote_github_repo(tmp_path) == "acme/widgets"

    def fake_run_https(cmd, **kwargs):
        return SimpleNamespace(stdout="https://github.com/acme/widgets\n", stderr="", returncode=0)

    monkeypatch.setattr(server.subprocess, "run", fake_run_https)
    assert server._git_remote_github_repo(tmp_path) == "acme/widgets"


def test_reject_records_policy_verdict(tmp_path, monkeypatch):
    psm = server.PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("RejectOrg", "reject audit")
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)
    proposal = ImprovementProposal(
        review_id=uuid4(),
        title="risky",
        description="d",
        priority="high",
        category="security",
        file_path="core/models/organization.py",
    )
    sm.save_improvement_proposal(proposal)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    response = client.post(f"/api/proposals/{org.name}/{str(proposal.id)[:8]}/reject")
    assert response.status_code == 200
    assert response.json()["policy"]["decision"] == "human_required"
    stored = json.loads(
        (sm.state_dir / "improvements" / f"{proposal.id}.json").read_text(encoding="utf-8")
    )
    assert stored.get("policy_decision") == "human_required"
    assert stored.get("status") == "rejected"
