"""A7/J7: 実行イベントに actor（誰が）を記録する監査ログ。"""

from __future__ import annotations

from fastapi.testclient import TestClient

import web.server as server

client = TestClient(server.app)


def test_normalizer_defaults_actor_to_system():
    norm = server._normalize_execution_history_item({"operation": "analysis_completed"})
    assert norm["actor"] == "system"
    norm2 = server._normalize_execution_history_item({"operation": "x", "actor": "user"})
    assert norm2["actor"] == "user"


async def test_record_execution_event_carries_actor(tmp_path, monkeypatch):
    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    rec = await server._record_execution_event("proposal_approved", "承認", actor="user")
    assert rec["actor"] == "user"

    rec_default = await server._record_execution_event("analysis_completed", "分析")
    assert rec_default["actor"] == "system"


def test_execution_history_endpoint_exposes_actor(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "s.json")
    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    server._append_execution_history({"operation": "proposal_approved", "title": "t", "actor": "user"})
    response = client.get("/api/execution-history")
    assert response.status_code == 200
    items = response.json()
    assert any(item.get("actor") == "user" for item in items)
