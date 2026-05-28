from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from core.models.organization import ImprovementProposal
from core.org_factory import create_default_organization
import web.server as server


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
    return [json.loads(line.removeprefix("data: ")) for line in body.splitlines() if line.startswith("data: ")]



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
        "running": False,
        "pid": 2222,
        "log_path": str(tmp_path / "daemon.log"),
    }
    assert killed == {"pid": 2222, "sig": server.signal.SIGTERM}
    assert not pid_file.exists()


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
        {"type": "start", "org": "demo-org"},
        {"type": "progress", "message": "Loading organization..."},
        {"type": "progress", "message": "Running code review..."},
        {"type": "progress", "message": "Saving generated proposals..."},
        {"type": "proposal", "data": {"id": "p1", "title": "First", "status": "proposed"}},
        {"type": "proposal", "data": {"id": "p2", "title": "Second", "status": "proposed"}},
        {"type": "done", "count": 2},
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
        {"type": "start", "goal": "Ship SSE support"},
        {"type": "progress", "message": "Planning goal execution..."},
        {"type": "progress", "message": "Saving goal history..."},
        {"type": "result", "data": goal_result},
        {"type": "done"},
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
    assert response.json() == [
        {"id": "proposed", "title": "Proposed proposal", "status": "proposed"},
        {"id": "pending", "title": "Pending proposal", "status": "pending"},
        {"id": "running", "title": "Running proposal", "status": "in_progress"},
    ]



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
        "change_summary": "Applied the requested improvement.",
        "branch": "feature/add-tests",
        "pr_url": "https://example.com/pr/1",
        "output": {
            "change_summary": "Applied the requested improvement.",
            "branch": "feature/add-tests",
            "pr_url": "https://example.com/pr/1",
        },
    }
    assert json.loads(proposal_path.read_text(encoding="utf-8"))["status"] == "done"


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
    monkeypatch.delenv("REPOCORP_DEFAULT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("REPOCORP_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json() == {
        "llm_provider": "anthropic",
        "llm_model": "claude-3-5-sonnet-20241022",
        "anthropic_api_key_masked": "",
        "openai_api_key_masked": "",
        "groq_api_key_masked": "",
        "github_models_api_key_masked": "",
        "gemini_api_key_masked": "",
        "anthropic_api_key_set": False,
        "openai_api_key_set": False,
        "groq_api_key_set": False,
        "github_models_api_key_set": False,
        "gemini_api_key_set": False,
        "daemon_interval": 3600,
        "daemon_max_files": 10,
        "settings_file": str(tmp_path / "settings.json"),
        "has_llm": False,
    }


def test_get_settings_masks_api_key(tmp_path, monkeypatch):
    """APIキーがマスクされて返されること"""
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps({
            "llm_provider": "anthropic",
            "llm_model": "claude-3-5-sonnet-20241022",
            "anthropic_api_key": "abcdefgh12345678",
        }),
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


def test_update_settings_saves_to_file(tmp_path, monkeypatch):
    """設定更新がファイルに保存されること"""
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(server, "SETTINGS_FILE", settings_file)
    monkeypatch.delenv("REPOCORP_DEFAULT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("REPOCORP_DEFAULT_MODEL", raising=False)

    response = client.put(
        "/api/settings",
        json={"llm_provider": "openai", "llm_model": "gpt-4o-mini"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "saved"
    assert json.loads(settings_file.read_text(encoding="utf-8")) == {
        "llm_provider": "openai",
        "llm_model": "gpt-4o-mini",
        "anthropic_api_key": "",
        "openai_api_key": "",
        "groq_api_key": "",
        "github_models_api_key": "",
        "gemini_api_key": "",
        "daemon_interval": 3600,
        "daemon_max_files": 10,
    }


def test_update_settings_sets_env_vars(tmp_path, monkeypatch):
    """設定更新が環境変数にも即時反映されること"""
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(server, "SETTINGS_FILE", settings_file)
    monkeypatch.delenv("REPOCORP_DEFAULT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    response = client.put(
        "/api/settings",
        json={"anthropic_api_key": "secret-key-1234"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "saved", "has_llm": True}
    assert server.os.environ["ANTHROPIC_API_KEY"] == "secret-key-1234"
    assert json.loads(settings_file.read_text(encoding="utf-8"))["anthropic_api_key"] == "secret-key-1234"



def test_settings_github_models_provider(tmp_path, monkeypatch):
    """github_models プロバイダーが設定に保存・取得できること"""
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(server, "SETTINGS_FILE", settings_file)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    response = client.put(
        "/api/settings",
        json={
            "llm_provider": "github_models",
            "llm_model": "gpt-4o",
            "github_models_api_key": "ghp_test_token_1234",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "saved", "has_llm": True}
    assert server.os.environ["GITHUB_TOKEN"] == "ghp_test_token_1234"

    get_response = client.get("/api/settings")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["llm_provider"] == "github_models"
    assert data["llm_model"] == "gpt-4o"
    assert data["github_models_api_key_set"] is True
    assert data["github_models_api_key_masked"] == "ghp_test...1234"
    assert json.loads(settings_file.read_text(encoding="utf-8"))["github_models_api_key"] == "ghp_test_token_1234"



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



def test_get_provider_models_anthropic_fallback(tmp_path, monkeypatch):
    """APIキーなしの場合はフォールバックリストが返ることを確認"""
    _reset_provider_model_state(tmp_path, monkeypatch)

    response = client.get("/api/providers/anthropic/models")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "anthropic"
    assert len(data["models"]) > 0
    assert data["source"] in ("fallback", "cache", "api")



def test_get_provider_models_openai_fallback(tmp_path, monkeypatch):
    _reset_provider_model_state(tmp_path, monkeypatch)

    response = client.get("/api/providers/openai/models")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "openai"
    assert len(data["models"]) > 0



def test_get_provider_models_groq_fallback(tmp_path, monkeypatch):
    _reset_provider_model_state(tmp_path, monkeypatch)

    response = client.get("/api/providers/groq/models")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "groq"
    assert len(data["models"]) > 0



def test_get_provider_models_github_models_fallback(tmp_path, monkeypatch):
    _reset_provider_model_state(tmp_path, monkeypatch)

    response = client.get("/api/providers/github_models/models")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "github_models"
    assert len(data["models"]) > 0



def test_get_provider_models_gemini_fallback(tmp_path, monkeypatch):
    """APIキーなしの場合はフォールバックリストが返ることを確認"""
    _reset_provider_model_state(tmp_path, monkeypatch)

    response = client.get("/api/providers/gemini/models")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "gemini"
    assert len(data["models"]) > 0
    assert any("gemini" in model for model in data["models"])



def test_get_provider_models_unknown(tmp_path, monkeypatch):
    _reset_provider_model_state(tmp_path, monkeypatch)

    response = client.get("/api/providers/unknown_provider/models")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "unknown_provider"
    assert data["models"] == []
    assert data["source"] == "unknown"



def test_get_provider_models_uses_cache(tmp_path, monkeypatch):
    _reset_provider_model_state(tmp_path, monkeypatch)

    first = client.get("/api/providers/openai/models")
    second = client.get("/api/providers/openai/models")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["source"] == "cache"



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
    assert (knowledge_dir / "test_temp_knowledge.md").read_text(encoding="utf-8") == "# 更新されたテスト"

    del_resp = client.delete("/api/knowledge/files/test_temp_knowledge.md")
    assert del_resp.status_code == 200
    assert not (knowledge_dir / "test_temp_knowledge.md").exists()

    after_del = client.get("/api/knowledge/files/test_temp_knowledge.md")
    assert after_del.status_code == 404
