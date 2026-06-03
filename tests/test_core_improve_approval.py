"""F5: Core 自己改善の承認→検証済み変更の直接適用（再生成回避）の統合テスト。

承認時に、サイドカー保存された validated_changes が実行タスクへそのまま渡り、
Core 自己改善は RepoCorp リポジトリ自身(PROJECT_ROOT)を対象にすることを検証する。
（実際の git 適用は FakeOrchestrator で差し替え、実リポジトリには触れない。）
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

import agents.orchestrator_agent as orchestrator_module
import web.server as server
from core.models.organization import ImprovementProposal
from core.org_factory import create_default_organization

client = TestClient(server.app)


def test_approval_passes_validated_changes_to_executor(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    org = create_default_organization("RepoCorp-Self", "self improvement")
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)

    proposal = ImprovementProposal(
        review_id=uuid4(),
        priority="high",
        category="core_self_improvement",
        title="Core 改善: docstring 追加",
        description="...",
        file_path="core/llm/base.py",
        expected_impact="x",
        implementation_difficulty="medium",
        status="proposed",
    )
    sm.save_improvement_proposal(proposal)
    server._save_validated_changes(
        sm,
        str(proposal.id),
        [{"file_path": "core/llm/base.py", "new_content": "X = 1\n"}],
        "bump",
    )

    captured: dict = {}

    class FakeOrchestrator:
        async def run(self, task):
            captured["task"] = task
            return SimpleNamespace(
                success=True,
                output={"branch": "repocorp/improvement-x", "files": ["core/llm/base.py"], "applied_validated": True},
                error=None,
            )

    monkeypatch.setattr(
        orchestrator_module.OrchestratorAgent,
        "create",
        classmethod(lambda cls, llm_client=None, **kwargs: FakeOrchestrator()),
    )

    response = client.post(f"/api/proposals/{org.name}/{proposal.id}/approve", json={})
    assert response.status_code == 200, response.text

    task = captured["task"]
    # 検証済み変更がそのまま実行タスクへ渡る（LLM 再生成しない）
    assert task.input["suggestion"]["validated_changes"] == [
        {"file_path": "core/llm/base.py", "new_content": "X = 1\n"}
    ]
    # Core 自己改善は RepoCorp リポジトリ自身を対象にする
    assert task.input["repo_path"] == str(server.PROJECT_ROOT)

    # 提案ステータスが done になっている
    body = response.json()
    assert body["status"] == "done"
