"""Tests for the WebGUI Core self-improvement dispatch (POST /api/core/improve)."""

from __future__ import annotations

from fastapi.testclient import TestClient

import web.server as server
from core.org_factory import create_default_organization

client = TestClient(server.app)

_ENV_KEYS = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY", "GITHUB_TOKEN", "GOOGLE_API_KEY"]


class _FakeAgentSuccess:
    """検証成功を返すフェイク CoreImprovementAgent（実LLM/pytestを回さない）。"""

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def run(self, task):
        from agents.base import AgentResult

        return AgentResult(
            success=True,
            output={
                "file_path": task.input["file_path"],
                "change_summary": "docstring を追加",
                "diff": "--- a/x\n+++ b/x\n@@\n+\"\"\"doc\"\"\"\n",
                "validated": True,
                "applied": False,
                "attempts": 1,
            },
        )


def _setup_platform(tmp_path, monkeypatch, *, with_org=True):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)
    org = None
    if with_org:
        org = create_default_organization("RepoCorp-Self", "self improvement")
        psm.save_organization(org)
    return psm, org


def test_core_improve_creates_human_required_proposal(tmp_path, monkeypatch):
    psm, org = _setup_platform(tmp_path, monkeypatch)
    monkeypatch.setattr("agents.core_improvement_agent.CoreImprovementAgent", _FakeAgentSuccess)

    response = client.post(
        "/api/core/improve",
        json={"instruction": "base.py に docstring を足す", "file_path": "core/llm/base.py"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["validated"] is True
    assert body["applied"] is False
    assert body["policy_decision"] == "human_required"  # Core変更は人間承認必須
    assert body["proposal_id"]
    assert body["org_name"] == "RepoCorp-Self"
    assert "core/llm/base.py" in body["file_path"]

    # 提案が pending として永続化される
    sm = psm.get_org_state_manager(org)
    pending = sm.get_pending_improvement_proposals(limit=10)
    assert any(
        p.get("file_path") == "core/llm/base.py" and p.get("category") == "core_self_improvement"
        for p in pending
    )


def test_core_improve_without_llm_returns_422(tmp_path, monkeypatch):
    # 実エージェント＋キー無し → LLM未設定で即失敗（pytestもファイルアクセスもしない）
    _setup_platform(tmp_path, monkeypatch)
    response = client.post(
        "/api/core/improve",
        json={"instruction": "x", "file_path": "core/llm/base.py"},
    )
    assert response.status_code == 422
    assert "LLM" in response.json()["detail"]


def test_core_improve_404_when_no_org(tmp_path, monkeypatch):
    _setup_platform(tmp_path, monkeypatch, with_org=False)
    response = client.post(
        "/api/core/improve",
        json={"instruction": "x", "file_path": "core/llm/base.py"},
    )
    assert response.status_code == 404


def test_core_improve_rejects_path_traversal(tmp_path, monkeypatch):
    _setup_platform(tmp_path, monkeypatch)
    response = client.post(
        "/api/core/improve",
        json={"instruction": "x", "file_path": "../escape.py"},
    )
    assert response.status_code == 422
