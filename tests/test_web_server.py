from __future__ import annotations

import base64
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

import web.server as server
from core.models.organization import ImprovementProposal
from core.org_factory import create_default_organization

client = TestClient(server.app)


def _reset_provider_model_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    server._model_cache.clear()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)


def _read_sse_events(body: str) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


def _set_knowledge_dir(tmp_path, monkeypatch) -> Path:
    knowledge_dir = tmp_path / "knowledge"
    monkeypatch.setattr(server, "KNOWLEDGE_DIR", knowledge_dir)
    return knowledge_dir


def _set_chat_sessions_dir(tmp_path, monkeypatch) -> Path:
    sessions_dir = tmp_path / "chat_sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(server, "CHAT_SESSIONS_DIR", sessions_dir)
    return sessions_dir


def _set_task_queue_home(tmp_path, monkeypatch) -> None:
    import core.orchestration.task_queue as task_queue_module

    monkeypatch.setattr(task_queue_module, "get_platform_home", lambda: tmp_path)


def test_get_storage_info(tmp_path, monkeypatch):
    settings_file = tmp_path / "gui_settings.json"
    settings_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(server, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(server, "get_platform_home", lambda: tmp_path)

    organizations_dir = tmp_path / "organizations"
    organizations_dir.mkdir(parents=True, exist_ok=True)
    (organizations_dir / "acme.json").write_text("{}", encoding="utf-8")

    chat_sessions_dir = _set_chat_sessions_dir(tmp_path, monkeypatch)
    (chat_sessions_dir / "session-1.json").write_text("{}", encoding="utf-8")

    knowledge_dir = _set_knowledge_dir(tmp_path, monkeypatch)
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    (knowledge_dir / "guide.md").write_text("# Guide", encoding="utf-8")

    (tmp_path / "task_queue.json").write_text("[]", encoding="utf-8")
    (tmp_path / "goal_history.json").write_text("[]", encoding="utf-8")

    resp = client.get("/api/storage/info")

    assert resp.status_code == 200
    data = resp.json()
    assert data["platform_home"] == str(tmp_path)
    assert "storage" in data
    assert "settings" in data["storage"]
    assert "chat_sessions" in data["storage"]
    assert "organizations" in data["storage"]
    assert data["storage"]["settings"]["exists"] is True
    assert data["storage"]["chat_sessions"]["file_count"] == 1
    assert data["storage"]["organizations"]["file_count"] == 1


def test_daemon_status_reports_running(tmp_path, monkeypatch):
    pid_file = tmp_path / "daemon.pid"
    pid_file.write_text("4321", encoding="utf-8")

    monkeypatch.setattr(server, "get_platform_home", lambda: tmp_path)
    monkeypatch.setattr(server.os, "kill", lambda pid, sig: None)

    response = client.get("/api/daemon/status")

    assert response.status_code == 200
    assert response.json() == {
        "running": True,
        "pid": 4321,
        "log_path": str(tmp_path / "daemon.log"),
    }


def test_daemon_start_uses_runner_command(tmp_path, monkeypatch):
    calls: dict[str, object] = {}

    class DummyProc:
        pid = 9876

    def fake_popen(cmd, cwd, stdout, stderr, start_new_session):
        calls["cmd"] = cmd
        calls["cwd"] = cwd
        calls["stderr"] = stderr
        calls["start_new_session"] = start_new_session
        calls["stdout_name"] = Path(stdout.name)
        return DummyProc()

    monkeypatch.setattr(server, "get_platform_home", lambda: tmp_path)
    monkeypatch.setattr(server.subprocess, "Popen", fake_popen)

    response = client.post("/api/daemon/start")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"
    assert data["message"] == "デーモンを起動しました。"
    assert data["running"] is True
    assert data["pid"] == 9876
    assert data["log_path"] == str(tmp_path / "daemon.log")
    assert data["interval"] == 3600
    assert data["max_files"] == 10
    assert (tmp_path / "daemon.pid").read_text(encoding="utf-8") == "9876"
    assert calls["cmd"] == [
        sys.executable,
        "-m",
        "core._daemon_runner",
        "--interval=3600",
        "--max-files=10",
    ]
    assert calls["cwd"] == server.PROJECT_ROOT
    assert calls["stderr"] == server.subprocess.STDOUT
    assert calls["start_new_session"] is True
    assert calls["stdout_name"] == tmp_path / "daemon.log"


def test_daemon_stop_terminates_pid_and_clears_pid_file(tmp_path, monkeypatch):
    pid_file = tmp_path / "daemon.pid"
    pid_file.write_text("2222", encoding="utf-8")
    killed: dict[str, int] = {}

    def fake_kill(pid, sig):
        killed["pid"] = pid
        killed["sig"] = sig

    monkeypatch.setattr(server, "get_platform_home", lambda: tmp_path)
    monkeypatch.setattr(server.os, "kill", fake_kill)

    response = client.post("/api/daemon/stop")

    assert response.status_code == 200
    assert response.json() == {
        "status": "stopped",
        "message": "デーモンを停止しました。",
        "running": False,
        "pid": 2222,
        "log_path": str(tmp_path / "daemon.log"),
    }
    assert killed == {"pid": 2222, "sig": server.signal.SIGTERM}
    assert not pid_file.exists()


def test_init_platform_response_includes_message(tmp_path, monkeypatch):
    import core.bootstrap as bootstrap_module

    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)
    monkeypatch.setattr(bootstrap_module, "bootstrap_platform", lambda: psm)

    response = client.post("/api/init")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "initialized"
    assert data["message"] == "プラットフォームを初期化しました。"
    assert data["platform_home"] == str(tmp_path)
    assert data["initialized"] is False


def test_handoff_api_create_approve_materializes(tmp_path, monkeypatch):
    """Web: handoff 作成 → 承認ボタンで approved ＋ 受け手 org にブリーフ提案を自動生成。"""
    from core.org_factory import create_default_organization

    home = tmp_path / "home"
    psm = server.PlatformStateManager(platform_home=home)
    repo = tmp_path / "note-org"
    repo.mkdir()
    target = create_default_organization("Note Sales", "note", repo_path=repo)
    psm.save_organization(target)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    # 作成 → pending（policy human_required）
    create = client.post(
        "/api/handoffs",
        json={
            "source_org": "SNS Growth",
            "target_org": "Note Sales",
            "kind": "audience_signal",
            "title": "検証済み需要: ChatGPT議事録",
            "payload": {"theme": "ChatGPTで議事録自動化"},
        },
    )
    assert create.status_code == 200, create.text
    handoff = create.json()
    assert handoff["status"] == "pending"
    assert handoff["policy_decision"] == "human_required"

    # 承認 → approved ＋ 受け手にブリーフ提案がマテリアライズされる
    approve = client.post(f"/api/handoffs/{handoff['handoff_id']}/approve")
    assert approve.status_code == 200, approve.text
    body = approve.json()
    assert body["status"] == "approved"
    assert body["materialized"] is not None
    assert body["materialized"]["org_name"] == "Note Sales"

    # 受け手 org の pending に content_asset 提案が積まれている
    sm = psm.get_org_state_manager(target)
    pending = sm.get_pending_improvement_proposals(limit=50)
    assert any(p.get("category") == "content_asset" for p in pending)

    # list で絞り込める
    listing = client.get("/api/handoffs", params={"target_org": "Note Sales"})
    assert listing.status_code == 200
    assert len(listing.json()) == 1


def test_handoff_api_approve_unknown_is_404(tmp_path, monkeypatch):
    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)
    resp = client.post("/api/handoffs/handoff:does-not-exist/approve")
    assert resp.status_code == 404


def test_handoff_api_approve_with_draft_makes_body(tmp_path, monkeypatch):
    """承認1ボタン: approve に draft=true を渡すと本文ドラフトまで作る（claude 不在＝決定論）。"""
    from core.org_factory import create_default_organization

    psm = server.PlatformStateManager(platform_home=tmp_path / "home")
    repo = tmp_path / "note-org"
    repo.mkdir()
    target = create_default_organization("Note Sales", "note", repo_path=repo)
    psm.save_organization(target)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    store = server._handoff_store()
    handoff = store.create(
        source_org="SNS Growth",
        target_org="Note Sales",
        kind="audience_signal",
        title="検証済み需要",
        payload={"theme": "AI議事録"},
    )
    resp = client.post(f"/api/handoffs/{handoff.handoff_id}/approve", json={"draft": True})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "approved"
    assert body["materialized"]["kind"] == "draft"
    assert body["materialized"]["file_path"].startswith("content/draft-")


def test_outcomes_import_api(tmp_path, monkeypatch):
    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)
    resp = client.post(
        "/api/outcomes/import",
        json={
            "org_name": "Note Sales",
            "rows": [
                {"metric": "revenue", "value": 3000},
                {"metric": "sales", "value": 4},
                {"metric": "", "value": 1},
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported"] == 2
    assert body["skipped"] == 1

    summary = client.get("/api/outcomes/Note Sales")
    assert summary.status_code == 200
    assert summary.json()["by_metric"]["revenue"]["sum"] == 3000


def test_handoff_api_draft_creates_body_proposal(tmp_path, monkeypatch):
    """Web: 本文生成エンドポイントが受け手 org に本文ドラフト提案を作る（claude 不在＝決定論）。"""
    from core.org_factory import create_default_organization

    home = tmp_path / "home"
    psm = server.PlatformStateManager(platform_home=home)
    repo = tmp_path / "note-org"
    repo.mkdir()
    target = create_default_organization("Note Sales", "note", repo_path=repo)
    psm.save_organization(target)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    store = server._handoff_store()
    handoff = store.create(
        source_org="SNS Growth",
        target_org="Note Sales",
        kind="audience_signal",
        title="検証済み需要",
        payload={"theme": "AI議事録"},
    )
    resp = client.post(f"/api/handoffs/{handoff.handoff_id}/draft")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["org_name"] == "Note Sales"
    assert body["file_path"].startswith("content/draft-")

    sm = psm.get_org_state_manager(target)
    assert any(
        p.get("category") == "content_asset"
        for p in sm.get_pending_improvement_proposals(limit=50)
    )


def test_analyze_stream_emits_sse_events(monkeypatch):
    async def fake_perform_analyze(req):
        assert req.org_name == "demo-org"
        return {
            "org_name": req.org_name,
            "files_reviewed": 2,
            "proposals_generated": 2,
            "generated_proposals": [
                {"id": "p1", "title": "First", "status": "proposed"},
                {"id": "p2", "title": "Second", "status": "proposed"},
            ],
        }

    monkeypatch.setattr(server, "_perform_analyze", fake_perform_analyze)

    response = client.post("/api/analyze/stream", json={"org_name": "demo-org", "max_files": 5})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["content-type"].startswith("text/event-stream")
    assert _read_sse_events(response.text) == [
        {
            "type": "start",
            "org": "demo-org",
            "org_name": "demo-org",
            "content": "demo-org の分析を開始します",
        },
        {
            "type": "progress",
            "message": "Loading organization...",
            "content": "Loading organization...",
        },
        {
            "type": "progress",
            "message": "Running code review...",
            "content": "Running code review...",
        },
        {
            "type": "progress",
            "message": "Saving generated proposals...",
            "content": "Saving generated proposals...",
        },
        {
            "type": "proposal",
            "org_name": "demo-org",
            "title": "First",
            "file_path": None,
            "content": "First",
            "data": {"id": "p1", "title": "First", "status": "proposed"},
        },
        {
            "type": "proposal",
            "org_name": "demo-org",
            "title": "Second",
            "file_path": None,
            "content": "Second",
            "data": {"id": "p2", "title": "Second", "status": "proposed"},
        },
        {
            "type": "done",
            "org_name": "demo-org",
            "files_reviewed": 2,
            "proposals_generated": 2,
            "count": 2,
            "content": "2 件のファイルを確認し、2 件の提案を生成しました",
        },
    ]


def test_goals_stream_emits_sse_events(monkeypatch):
    goal_result = {
        "goal_text": "Ship SSE support",
        "summary": "done",
        "success": True,
        "goal_type": "feature",
        "scale": "medium",
        "organization": "Platform",
        "done_count": 3,
        "total": 3,
        "failed_count": 0,
        "achievement_pct": 100.0,
        "recommendations": [],
        "created_at": "2025-01-01T00:00:00+00:00",
    }

    async def fake_perform_goal_run(req):
        assert req.goal_text == "Ship SSE support"
        return goal_result

    monkeypatch.setattr(server, "_perform_goal_run", fake_perform_goal_run)

    response = client.post("/api/goals/stream", json={"goal_text": "Ship SSE support"})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["content-type"].startswith("text/event-stream")
    assert _read_sse_events(response.text) == [
        {"type": "start", "goal": "Ship SSE support", "org_name": None},
        {
            "type": "progress",
            "message": "Planning goal execution...",
            "content": "Planning goal execution...",
        },
        {
            "type": "progress",
            "message": "Saving goal history...",
            "content": "Saving goal history...",
        },
        {
            "type": "result",
            "goal": "Ship SSE support",
            "org_name": "Platform",
            "result": "done",
            "summary": "done",
            "content": "done",
            "data": goal_result,
        },
        {
            "type": "done",
            "goal": "Ship SSE support",
            "org_name": "Platform",
            "result": "done",
            "content": "ゴール実行が完了しました",
        },
    ]


def test_chat_session_crud(tmp_path, monkeypatch):
    _set_chat_sessions_dir(tmp_path, monkeypatch)

    create_resp = client.post("/api/chat/sessions", json={"name": "テストセッション"})
    assert create_resp.status_code == 200
    session_id = create_resp.json()["id"]

    list_resp = client.get("/api/chat/sessions")
    assert list_resp.status_code == 200
    assert any(session["id"] == session_id for session in list_resp.json()["sessions"])

    get_resp = client.get(f"/api/chat/sessions/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "テストセッション"

    delete_resp = client.delete(f"/api/chat/sessions/{session_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json() == {"status": "ok"}

    missing_resp = client.get(f"/api/chat/sessions/{session_id}")
    assert missing_resp.status_code == 404


def test_update_chat_session_name(tmp_path, monkeypatch):
    _set_chat_sessions_dir(tmp_path, monkeypatch)

    create_resp = client.post("/api/chat/sessions", json={"name": "元の名前"})
    assert create_resp.status_code == 200
    session_id = create_resp.json()["id"]

    update_resp = client.put(f"/api/chat/sessions/{session_id}", json={"name": "新しい名前"})
    assert update_resp.status_code == 200
    assert update_resp.json() == {"id": session_id, "name": "新しい名前"}

    get_resp = client.get(f"/api/chat/sessions/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "新しい名前"

    err_resp = client.put(f"/api/chat/sessions/{session_id}", json={"name": ""})
    assert err_resp.status_code == 400

    delete_resp = client.delete(f"/api/chat/sessions/{session_id}")
    assert delete_resp.status_code == 200


def test_chat_session_add_message(tmp_path, monkeypatch):
    _set_chat_sessions_dir(tmp_path, monkeypatch)

    async def fake_process_chat_message(message, session_context=None):
        assert message == "組織のコードをレビューして"
        assert session_context == []
        return "レビューを開始します"

    monkeypatch.setattr(server, "_process_chat_message", fake_process_chat_message)

    create_resp = client.post("/api/chat/sessions", json={"name": ""})
    session_id = create_resp.json()["id"]

    message_resp = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": "組織のコードをレビューして", "role": "user"},
    )

    assert message_resp.status_code == 200
    payload = message_resp.json()
    assert payload["user_message"]["content"] == "組織のコードをレビューして"
    assert payload["assistant_message"]["content"] == "レビューを開始します"

    session_resp = client.get(f"/api/chat/sessions/{session_id}")
    assert session_resp.status_code == 200
    session = session_resp.json()
    assert session["name"] == "組織のコードをレビューして"
    assert [message["role"] for message in session["messages"]] == ["user", "assistant"]


def test_chat_endpoint_rejects_blank_message(monkeypatch):
    called = {"value": False}

    async def fake_process_chat_message(message, session_context=None):
        called["value"] = True
        return "should not run"

    monkeypatch.setattr(server, "_process_chat_message", fake_process_chat_message)

    response = client.post("/api/chat", json={"message": "   "})

    assert response.status_code == 400
    assert response.json() == {"detail": "メッセージを入力してください"}
    assert called["value"] is False


def test_list_proposals_returns_only_active_statuses(monkeypatch):
    monkeypatch.setattr(
        server,
        "_pending_proposals_for",
        lambda org_name: (
            None,
            None,
            [
                {"id": "proposed", "title": "Proposed proposal", "status": "proposed"},
                {"id": "pending", "title": "Pending proposal", "status": "pending"},
                {"id": "running", "title": "Running proposal", "status": "in_progress"},
                {"id": "done", "title": "Done proposal", "status": "done"},
                {"id": "rejected", "title": "Rejected proposal", "status": "rejected"},
            ],
        ),
    )

    response = client.get("/api/organizations/demo-org/proposals")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == ["proposed", "pending", "running"]
    assert [item["status"] for item in payload] == ["proposed", "pending", "in_progress"]
    assert all("diff_text" in item for item in payload)
    assert all("approval_notes" in item for item in payload)


def test_list_organizations_counts_only_active_proposals(tmp_path, monkeypatch):
    psm = server.PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("Count Org", "Count active proposals")
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)
    for title, status in [
        ("Proposed", "proposed"),
        ("Pending", "pending"),
        ("Running", "in_progress"),
        ("Done", "done"),
        ("Rejected", "rejected"),
        ("Failed", "failed"),
        ("Cancelled", "cancelled"),
    ]:
        sm.save_improvement_proposal(
            ImprovementProposal(
                review_id=uuid4(),
                title=title,
                description="status coverage",
                file_path="core/example.py",
                status=status,
            )
        )
    monkeypatch.setattr(server, "_psm", lambda: psm)

    response = client.get("/api/organizations")

    assert response.status_code == 200
    assert response.json()[0]["pending_proposals"] == 3


def test_get_organization_includes_division_tree(tmp_path, monkeypatch):
    psm = server.PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("Tree Org", "Inspect hierarchy")
    psm.save_organization(org)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    response = client.get(f"/api/organizations/{org.name}")

    assert response.status_code == 200
    data = response.json()
    assert data["divisions"]
    first_division = data["divisions"][0]
    assert first_division["teams"]
    assert first_division["teams"][0]["agents"]


def test_runtime_agents_endpoint_returns_status_and_proficiency(tmp_path, monkeypatch):
    psm = server.PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("Runtime Org", "Track runtime agents")
    runtime_agent = org.divisions[0].teams[0].agents[0]
    runtime_agent.current_task = "Investigate regressions"
    runtime_agent.performance_score = 88
    psm.save_organization(org)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    response = client.get("/api/agents/runtime")

    assert response.status_code == 200
    data = response.json()
    assert data[0]["organization"] == "Runtime Org"
    assert data[0]["status"] == "running"
    assert data[0]["proficiency"] == 88
    assert data[0]["configuration"]["current_task"] == "Investigate regressions"


def test_approve_proposal_runs_without_request_body(tmp_path, monkeypatch):
    import agents.orchestrator_agent as orchestrator_module

    psm = server.PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("ApproveOrg", "Apply proposal")
    org.target_repo_path = str(tmp_path / "repo")
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)
    proposal = ImprovementProposal(
        review_id=uuid4(),
        title="Add tests",
        description="Increase coverage for the dashboard page.",
        priority="high",
        category="quality",
        file_path="src/pages/DashboardPage.tsx",
    )
    proposal_path = sm.save_improvement_proposal(proposal)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    class FakeOrchestrator:
        async def run(self, task):
            return SimpleNamespace(
                success=True,
                output={
                    "change_summary": "Applied the requested improvement.",
                    "branch": "feature/add-tests",
                    "pr_url": "https://example.com/pr/1",
                },
                error=None,
            )

    def fake_create(cls, llm_client=None, **kwargs):
        return FakeOrchestrator()

    monkeypatch.setattr(orchestrator_module.OrchestratorAgent, "create", classmethod(fake_create))

    response = client.post(f"/api/proposals/{org.name}/{str(proposal.id)[:8]}/approve")

    assert response.status_code == 200
    assert response.json() == {
        "status": "done",
        "proposal_id": str(proposal.id),
        "title": "Add tests",
        "approval_notes": "",
        "change_summary": "Applied the requested improvement.",
        "branch": "feature/add-tests",
        "pr_url": "https://example.com/pr/1",
        "output": {
            "change_summary": "Applied the requested improvement.",
            "branch": "feature/add-tests",
            "pr_url": "https://example.com/pr/1",
        },
        "policy": {
            "decision": "human_required",
            "reason": "優先度 'high' は人間確認必須",
            "rule": "human_required.min_priority",
        },
    }
    assert json.loads(proposal_path.read_text(encoding="utf-8"))["status"] == "done"


def test_approve_proposal_persists_approval_notes(tmp_path, monkeypatch):
    import agents.orchestrator_agent as orchestrator_module

    psm = server.PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("ApproveNotesOrg", "Apply proposal with notes")
    org.target_repo_path = str(tmp_path / "repo")
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)
    proposal = ImprovementProposal(
        review_id=uuid4(),
        title="Add docs",
        description="Document the new workflow.",
        priority="low",
        category="documentation",
        file_path="docs/workflow.md",
    )
    proposal_path = sm.save_improvement_proposal(proposal)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    class FakeOrchestrator:
        async def run(self, task):
            return SimpleNamespace(success=True, output={}, error=None)

    monkeypatch.setattr(
        orchestrator_module.OrchestratorAgent,
        "create",
        classmethod(lambda cls, llm_client=None, **kwargs: FakeOrchestrator()),
    )

    response = client.post(
        f"/api/proposals/{org.name}/{str(proposal.id)[:8]}/approve",
        json={"approval_notes": "Ship after smoke test."},
    )

    assert response.status_code == 200
    assert response.json()["approval_notes"] == "Ship after smoke test."
    stored = json.loads(proposal_path.read_text(encoding="utf-8"))
    assert stored["approval_notes"] == "Ship after smoke test."


def test_welcome_creates_sample_org(tmp_path, monkeypatch):
    """ウェルカムエンドポイントがサンプル組織を作成すること"""
    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    response = client.post("/api/welcome")

    assert response.status_code == 200
    assert response.json() == {
        "created": ["Sample Organization"],
        "skipped": [],
    }
    saved = psm.load_organization_by_name("Sample Organization")
    assert saved is not None
    assert saved.target_repo_path == str(server.PROJECT_ROOT)
    assert saved.is_system is False


def test_welcome_skips_existing_org(tmp_path, monkeypatch):
    """すでに同名組織がある場合はスキップすること"""
    psm = server.PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("Sample Organization", "existing org")
    psm.save_organization(org)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    response = client.post("/api/welcome")

    assert response.status_code == 200
    assert response.json() == {
        "created": [],
        "skipped": ["Sample Organization"],
    }


def test_get_settings_returns_defaults(tmp_path, monkeypatch):
    """設定ファイルがない場合はデフォルト値を返すこと"""
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.delenv("PANTHEON_DEFAULT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("PANTHEON_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    response = client.get("/api/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm_provider"] == "anthropic"
    assert payload["llm_model"] == "claude-3-5-sonnet-20241022"
    assert payload["anthropic_api_key_masked"] == ""
    assert payload["openai_api_key_masked"] == ""
    assert payload["groq_api_key_masked"] == ""
    assert payload["github_models_api_key_masked"] == ""
    assert payload["gemini_api_key_masked"] == ""
    assert payload["anthropic_api_key_set"] is False
    assert payload["openai_api_key_set"] is False
    assert payload["groq_api_key_set"] is False
    assert payload["github_models_api_key_set"] is False
    assert payload["gemini_api_key_set"] is False
    assert payload["daemon_interval"] == 3600
    assert payload["daemon_max_files"] == 10
    assert payload["settings_file"] == str(tmp_path / "settings.json")
    assert payload["has_llm"] is False
    assert isinstance(payload["model_configurations"], dict)
    assert isinstance(payload["prompt_templates"], dict)
    assert isinstance(payload["policy_rules"], dict)


def test_get_settings_masks_api_key(tmp_path, monkeypatch):
    """APIキーがマスクされて返されること"""
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "llm_provider": "anthropic",
                "llm_model": "claude-3-5-sonnet-20241022",
                "anthropic_api_key": "abcdefgh12345678",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "SETTINGS_FILE", settings_file)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    response = client.get("/api/settings")

    assert response.status_code == 200
    data = response.json()
    assert data["anthropic_api_key_masked"] == "abcdefgh...5678"
    assert data["anthropic_api_key_set"] is True


def test_cors_preflight_allows_localhost_origin():
    response = client.options(
        "/api/settings",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_get_settings_warns_on_open_permissions(tmp_path, monkeypatch, caplog):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{}", encoding="utf-8")
    settings_file.chmod(0o644)
    monkeypatch.setattr(server, "SETTINGS_FILE", settings_file)

    with caplog.at_level(logging.WARNING):
        response = client.get("/api/settings")

    assert response.status_code == 200
    assert "expected 0o600" in caplog.text


def test_update_settings_saves_to_file(tmp_path, monkeypatch):
    """設定更新がファイルに保存されること"""
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(server, "SETTINGS_FILE", settings_file)
    monkeypatch.delenv("PANTHEON_DEFAULT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("PANTHEON_DEFAULT_MODEL", raising=False)

    response = client.put(
        "/api/settings",
        json={"llm_provider": "openai", "llm_model": "gpt-4o-mini"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "saved"

    saved = json.loads(settings_file.read_text(encoding="utf-8"))
    assert saved["llm_provider"] == "openai"
    assert saved["llm_model"] == "gpt-4o-mini"
    assert saved["anthropic_api_key"] == ""
    assert saved["openai_api_key"] == ""
    assert saved["groq_api_key"] == ""
    assert saved["github_models_api_key"] == ""
    assert saved["gemini_api_key"] == ""
    assert saved["daemon_interval"] == 3600
    assert saved["daemon_max_files"] == 10
    assert isinstance(saved["model_configurations"], dict)
    assert isinstance(saved["prompt_templates"], dict)
    assert isinstance(saved["policy_rules"], dict)


def test_update_settings_persists_model(tmp_path, monkeypatch):
    """設定更新（モデル）が保存されること。Pantheon は Claude Code 前提で API キーは扱わない。"""
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(server, "SETTINGS_FILE", settings_file)

    response = client.put(
        "/api/settings",
        json={"llm_model": "claude-opus-4-8"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "saved"
    assert "has_llm" in body
    assert json.loads(settings_file.read_text(encoding="utf-8"))["llm_model"] == "claude-opus-4-8"


def test_update_settings_sets_restrictive_permissions(tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(server, "SETTINGS_FILE", settings_file)

    response = client.put(
        "/api/settings",
        json={"llm_provider": "openai"},
    )

    assert response.status_code == 200
    assert settings_file.stat().st_mode & 0o777 == 0o600


def test_settings_roundtrip_is_claude_code_only(tmp_path, monkeypatch):
    """設定は Claude Code 前提（マルチプロバイダ / API キー UI は廃止）。"""
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(server, "SETTINGS_FILE", settings_file)

    response = client.put("/api/settings", json={"llm_model": "claude-sonnet-4-6"})
    assert response.status_code == 200

    get_response = client.get("/api/settings")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["llm_model"] == "claude-sonnet-4-6"
    # has_llm reflects the local claude CLI (disabled in tests via PANTHEON_NO_CLAUDE).
    assert isinstance(data["has_llm"], bool)


def test_queue_and_list_tasks(tmp_path, monkeypatch):
    _set_task_queue_home(tmp_path, monkeypatch)

    resp = client.post(
        "/api/tasks",
        json={
            "task_type": "analyze",
            "org_name": "TestOrg",
            "description": "テスト分析タスク",
        },
    )
    assert resp.status_code == 200
    task_id = resp.json()["id"]

    list_resp = client.get("/api/tasks")
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert "tasks" in payload
    assert "stats" in payload
    assert payload["stats"]["total"] == 1
    assert payload["stats"]["pending"] == 1

    get_resp = client.get(f"/api/tasks/{task_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == task_id

    cancel_resp = client.delete(f"/api/tasks/{task_id}")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json() == {"status": "cancelled", "task_id": task_id}


def test_get_task_not_found(tmp_path, monkeypatch):
    _set_task_queue_home(tmp_path, monkeypatch)

    resp = client.get("/api/tasks/nonexistent-id")
    assert resp.status_code == 404


def test_get_provider_models_returns_claude_models(tmp_path, monkeypatch):
    """API 排除後はプロバイダに関わらず Claude Code のモデル一覧を返す。"""
    response = client.get("/api/providers/anything/models")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "claude_code"
    assert len(data["models"]) > 0
    assert any("claude" in model for model in data["models"])
    assert data["source"] in ("claude-code", "unavailable")


def test_list_organizations_includes_system_flag(tmp_path, monkeypatch):
    """組織一覧に is_system が含まれること"""
    psm = server.PlatformStateManager(platform_home=tmp_path)
    psm.save_organization(create_default_organization("Protected Org", "Core", is_system=True))
    psm.save_organization(create_default_organization("Editable Org", "User created"))
    monkeypatch.setattr(server, "_psm", lambda: psm)

    response = client.get("/api/organizations")

    assert response.status_code == 200
    payload = {org["name"]: org for org in response.json()}
    assert payload["Protected Org"]["is_system"] is True
    assert payload["Editable Org"]["is_system"] is False


def test_get_organization_detail_returns_agents(tmp_path, monkeypatch):
    """組織詳細にエージェント一覧が含まれること"""
    psm = server.PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("Detail Org", "Inspect agents")
    org.target_repo_path = str(tmp_path / "repo")
    psm.save_organization(org)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    response = client.get("/api/organizations/Detail Org")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Detail Org"
    assert data["purpose"] == "Inspect agents"
    assert data["total_agents"] == 1
    assert data["pending_proposals"] == 0
    assert data["is_system"] is False
    assert len(data["agents"]) == 1
    assert data["agents"][0]["name"] == "General Specialist"
    assert data["agents"][0]["capability_id"] == "General Specialist"
    assert data["agents"][0]["skills"] == ["strategic_planning", "deep_research"]


def test_get_org_icon_autogenerated(tmp_path, monkeypatch):
    """アイコンエンドポイントが自動生成SVGを返すことを確認"""
    psm = server.PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("Pixel Org", "Auto icon")
    psm.save_organization(org)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    response = client.get("/api/organizations/Pixel Org/icon")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.text.startswith("<svg")
    assert '<rect width="32" height="32" fill="#1e1e2e" rx="2"/>' in response.text


def test_set_and_delete_org_icon(tmp_path, monkeypatch):
    """カスタムアイコンの設定・削除"""
    psm = server.PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("Icon Org", "Custom icon")
    psm.save_organization(org)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    icon_bytes = b"fake-png-data"
    icon_data = f"data:image/png;base64,{base64.b64encode(icon_bytes).decode('ascii')}"

    set_response = client.put("/api/organizations/Icon Org/icon", json={"icon_data": icon_data})
    assert set_response.status_code == 200
    assert set_response.json() == {"status": "ok"}

    saved = psm.load_organization_by_name("Icon Org")
    assert saved is not None
    assert saved.icon_data == icon_data

    get_response = client.get("/api/organizations/Icon Org/icon")
    assert get_response.status_code == 200
    assert get_response.headers["content-type"].startswith("image/png")
    assert get_response.content == icon_bytes

    delete_response = client.delete("/api/organizations/Icon Org/icon")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "ok"}

    reset = psm.load_organization_by_name("Icon Org")
    assert reset is not None
    assert reset.icon_data == ""

    regenerated = client.get("/api/organizations/Icon Org/icon")
    assert regenerated.status_code == 200
    assert regenerated.headers["content-type"].startswith("image/svg+xml")


def test_get_organization_detail_404_for_missing(tmp_path, monkeypatch):
    """存在しない組織名で404が返ること"""
    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    response = client.get("/api/organizations/missing-org")

    assert response.status_code == 404
    assert response.json() == {"detail": "Organization 'missing-org' が見つかりません"}


def test_delete_system_org_forbidden(tmp_path, monkeypatch):
    """システム組織は削除できないことを確認"""
    psm = server.PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("Protected Org", "Core operations", is_system=True)
    psm.save_organization(org)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    response = client.delete("/api/organizations/Protected Org")

    assert response.status_code == 403
    assert response.json() == {"detail": "システム組織「Protected Org」は削除できません。"}
    assert psm.load_organization_by_name("Protected Org") is not None


def test_delete_org_requires_existing(tmp_path, monkeypatch):
    """存在しない組織の削除は404"""
    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    response = client.delete("/api/organizations/nonexistent-org-xyz")

    assert response.status_code == 404
    assert response.json() == {"detail": "Organization 'nonexistent-org-xyz' が見つかりません"}


def test_migrate_system_orgs_marks_meta_org(tmp_path):
    """既存のメタ組織に is_system=True を付与できること"""
    psm = server.PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("Meta-Improvement Organization", "Core operations")
    raw = json.loads(org.model_dump_json())
    raw.pop("is_system", None)
    (psm.orgs_dir / f"{org.id}.json").write_text(json.dumps(raw), encoding="utf-8")
    psm.initialize(meta_improvement_org_id=str(org.id))

    server._migrate_system_orgs(psm)

    migrated = psm.load_organization_by_name("Meta-Improvement Organization")
    assert migrated is not None
    assert migrated.is_system is True


def test_update_organization_purpose(tmp_path, monkeypatch):
    """目的フィールドを更新できること"""
    psm = server.PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("Editable Org", "Old purpose")
    psm.save_organization(org)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    response = client.put("/api/organizations/Editable Org", json={"purpose": "New purpose"})

    assert response.status_code == 200
    assert response.json()["status"] == "updated"
    updated = psm.load_organization_by_name("Editable Org")
    assert updated is not None
    assert updated.purpose == "New purpose"


def test_update_organization_404_for_missing(tmp_path, monkeypatch):
    """存在しない組織名で404が返ること"""
    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    response = client.put("/api/organizations/missing-org", json={"purpose": "New purpose"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Organization 'missing-org' が見つかりません"}


def test_goal_history_normalizes_summary_records(tmp_path, monkeypatch):
    history_file = tmp_path / "goal_history.json"
    history_file.write_text(
        json.dumps(
            [
                {
                    "goal_text": "品質を改善する",
                    "summary": "改善提案を作成しました",
                    "organization": "Platform",
                    "created_at": "2025-01-01T00:00:00+00:00",
                    "success": True,
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "_goal_history_path", lambda: history_file)

    response = client.get("/api/goals/history")

    assert response.status_code == 200
    assert response.json() == [
        {
            "goal": "品質を改善する",
            "goal_text": "品質を改善する",
            "result": "改善提案を作成しました",
            "summary": "改善提案を作成しました",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "created_at": "2025-01-01T00:00:00+00:00",
            "org_name": "Platform",
            "organization": "Platform",
            "success": True,
            "goal_type": None,
            "scale": None,
            "done_count": None,
            "total": None,
            "failed_count": None,
            "achievement_pct": None,
            "recommendations": [],
            "id": None,
        }
    ]


def test_clear_goal_history_creates_empty_file(tmp_path, monkeypatch):
    """履歴削除後に空のJSONファイルが作られること"""
    history_file = tmp_path / "goal_history.json"
    history_file.write_text(json.dumps([{"goal_text": "before"}]), encoding="utf-8")
    monkeypatch.setattr(server, "_goal_history_path", lambda: history_file)

    response = client.delete("/api/goals/history")

    assert response.status_code == 200
    assert response.json() == {"status": "cleared"}
    assert history_file.exists()
    assert json.loads(history_file.read_text(encoding="utf-8")) == []


def test_clear_goal_history_when_no_file(tmp_path, monkeypatch):
    """ファイルが存在しない場合もエラーにならないこと"""
    history_file = tmp_path / "goal_history.json"
    monkeypatch.setattr(server, "_goal_history_path", lambda: history_file)

    response = client.delete("/api/goals/history")

    assert response.status_code == 200
    assert response.json() == {"status": "cleared"}
    assert not history_file.exists()


def test_list_knowledge_files(tmp_path, monkeypatch):
    """knowledge ファイル一覧が取得できることを確認"""
    knowledge_dir = _set_knowledge_dir(tmp_path, monkeypatch)
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")
    (knowledge_dir / "ignore.txt").write_text("ignore", encoding="utf-8")

    response = client.get("/api/knowledge/files")

    assert response.status_code == 200
    data = response.json()
    assert "files" in data
    assert isinstance(data["files"], list)
    assert [item["name"] for item in data["files"]] == ["alpha.md"]


def test_get_knowledge_file_not_found(tmp_path, monkeypatch):
    _set_knowledge_dir(tmp_path, monkeypatch)

    response = client.get("/api/knowledge/files/nonexistent.md")

    assert response.status_code == 404


def test_knowledge_file_path_traversal(tmp_path, monkeypatch):
    """パストラバーサル攻撃が防がれることを確認"""
    _set_knowledge_dir(tmp_path, monkeypatch)

    response = client.get("/api/knowledge/files/%2E%2E/%2E%2E/etc/passwd")

    assert response.status_code in (400, 404)


def test_create_and_delete_knowledge_file(tmp_path, monkeypatch):
    """ファイル作成・更新・削除の正常系テスト"""
    knowledge_dir = _set_knowledge_dir(tmp_path, monkeypatch)

    response = client.post(
        "/api/knowledge/files",
        json={
            "name": "test_temp_knowledge.md",
            "content": "# テスト\nこれはテストです。",
        },
    )
    assert response.status_code == 200
    assert (knowledge_dir / "test_temp_knowledge.md").exists()

    get_resp = client.get("/api/knowledge/files/test_temp_knowledge.md")
    assert get_resp.status_code == 200
    assert "テスト" in get_resp.json()["content"]

    put_resp = client.put(
        "/api/knowledge/files/test_temp_knowledge.md",
        json={"content": "# 更新されたテスト"},
    )
    assert put_resp.status_code == 200
    assert (knowledge_dir / "test_temp_knowledge.md").read_text(
        encoding="utf-8"
    ) == "# 更新されたテスト"

    del_resp = client.delete("/api/knowledge/files/test_temp_knowledge.md")
    assert del_resp.status_code == 200
    assert not (knowledge_dir / "test_temp_knowledge.md").exists()

    after_del = client.get("/api/knowledge/files/test_temp_knowledge.md")
    assert after_del.status_code == 404


def test_create_knowledge_file_rejects_non_markdown_extension(tmp_path, monkeypatch):
    _set_knowledge_dir(tmp_path, monkeypatch)

    response = client.post(
        "/api/knowledge/files",
        json={
            "name": "notes.txt",
            "content": "blocked",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Markdown ファイルのみ作成できます"}


def test_create_organization_rejects_parent_traversal_path():
    response = client.post(
        "/api/organizations",
        json={
            "name": "Unsafe Org",
            "purpose": "reject traversal",
            "target_repo_path": "../outside-repo",
        },
    )

    assert response.status_code == 422


def test_queue_task_rejects_invalid_task_type(tmp_path, monkeypatch):
    _set_task_queue_home(tmp_path, monkeypatch)

    response = client.post(
        "/api/tasks",
        json={
            "task_type": "../escape",
            "org_name": "TestOrg",
            "description": "bad task type",
        },
    )

    assert response.status_code == 422


def test_run_goal_rejects_overlong_goal_text():
    response = client.post("/api/goals/run", json={"goal_text": "x" * 4001})

    assert response.status_code == 422


def test_create_knowledge_file_rejects_parent_traversal_name(tmp_path, monkeypatch):
    _set_knowledge_dir(tmp_path, monkeypatch)

    response = client.post(
        "/api/knowledge/files",
        json={
            "name": "../escape.md",
            "content": "blocked",
        },
    )

    assert response.status_code == 422


def test_execution_history_endpoint_combines_saved_history_and_goal_history(tmp_path, monkeypatch):
    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)
    _set_task_queue_home(tmp_path, monkeypatch)

    (tmp_path / "execution_history.json").write_text(
        json.dumps(
            [
                {
                    "id": "evt-1",
                    "timestamp": "2025-01-03T10:00:00+00:00",
                    "operation": "organization_created",
                    "status": "success",
                    "title": "Created alpha",
                    "details": "alpha created",
                    "org_name": "alpha",
                    "entity_type": "organization",
                    "entity_id": "alpha",
                    "route": "/orgs",
                    "metadata": {},
                }
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "goal_history.json").write_text(
        json.dumps(
            [
                {
                    "goal": "Ship search",
                    "result": "Search shipped",
                    "timestamp": "2025-01-02T10:00:00+00:00",
                    "org_name": "alpha",
                    "success": True,
                }
            ]
        ),
        encoding="utf-8",
    )

    response = client.get("/api/execution-history")

    assert response.status_code == 200
    data = response.json()
    assert data[0]["operation"] == "organization_created"
    assert any(item["operation"] == "goal_completed" for item in data)


def test_search_endpoint_returns_matching_entities(tmp_path, monkeypatch):
    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    org = create_default_organization("alpha-org", "General search improvements")
    psm.save_organization(org)

    proposal = ImprovementProposal(
        review_id=uuid4(),
        title="General search audit trail",
        description="Index proposals and goals",
        file_path="web/server.py",
        status="proposed",
    )
    psm.get_org_state_manager(org).save_improvement_proposal(proposal)
    (tmp_path / "goal_history.json").write_text(
        json.dumps(
            [
                {
                    "goal": "Improve general search",
                    "result": "Search launched",
                    "timestamp": "2025-01-01T00:00:00+00:00",
                    "org_name": "alpha-org",
                    "success": True,
                }
            ]
        ),
        encoding="utf-8",
    )

    response = client.get("/api/search", params={"q": "general"})

    assert response.status_code == 200
    types = {item["type"] for item in response.json()}
    assert {"organization", "agent", "proposal", "goal"}.issubset(types)


def test_batch_reject_proposals_updates_multiple_entries(tmp_path, monkeypatch):
    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    org = create_default_organization("batch-org", "Batch proposal updates")
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)
    proposal_one = ImprovementProposal(
        review_id=uuid4(), title="First", description="One", file_path="a.py", status="proposed"
    )
    proposal_two = ImprovementProposal(
        review_id=uuid4(), title="Second", description="Two", file_path="b.py", status="pending"
    )
    sm.save_improvement_proposal(proposal_one)
    sm.save_improvement_proposal(proposal_two)

    response = client.post(
        f"/api/proposals/{org.name}/batch",
        json={
            "proposal_ids": [str(proposal_one.id), str(proposal_two.id)],
            "action": "reject",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["updated"] == 2
    proposals = client.get(f"/api/organizations/{org.name}/proposals")
    assert proposals.status_code == 200
    assert proposals.json() == []


def test_updates_websocket_receives_task_queue_events(tmp_path, monkeypatch):
    _set_task_queue_home(tmp_path, monkeypatch)
    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    with client.websocket_connect("/ws/updates") as websocket:
        initial = websocket.receive_json()
        assert initial["status"] == "connected"

        response = client.post(
            "/api/tasks",
            json={
                "task_type": "custom",
                "org_name": "alpha-org",
                "description": "Queue searchable task",
                "priority": 5,
            },
        )

        assert response.status_code == 200
        event = websocket.receive_json()
        assert event["type"] == "task_queued"
        assert event["title"] == "Queue searchable task"


def test_analyze_routes_through_orchestrator(tmp_path, monkeypatch):
    """POST /api/analyze は CodeReviewAgent を直接呼ばず OrchestratorAgent 経由で実行する。"""
    import agents.orchestrator_agent as orchestrator_module

    psm = server.PlatformStateManager(platform_home=tmp_path)
    org = create_default_organization("RouteOrg", "route analyze")
    org.target_repo_path = str(tmp_path)
    psm.save_organization(org)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    calls = {"created": 0}

    class SpyOrchestrator:
        async def run(self, task):
            assert task.task_type == "code_review"
            return SimpleNamespace(
                success=True,
                output={
                    "suggestions": [
                        {
                            "title": "Tidy",
                            "description": "d",
                            "file_path": "a.py",
                            "priority": "low",
                        }
                    ]
                },
                error=None,
            )

    def fake_create(cls, llm_client=None, **kwargs):
        calls["created"] += 1
        return SpyOrchestrator()

    monkeypatch.setattr(orchestrator_module.OrchestratorAgent, "create", classmethod(fake_create))

    response = client.post("/api/analyze", json={"org_name": "RouteOrg", "max_files": 3})
    assert response.status_code == 200
    assert calls["created"] == 1  # OrchestratorAgent 経由で実行された
    assert response.json()["proposals_generated"] == 1
