from __future__ import annotations

from fastapi.testclient import TestClient

import web.server as server

client = TestClient(server.app)


def test_orchestra_endpoint_shape(tmp_path, monkeypatch):
    """/api/dashboard/orchestra は sessions / handoffs / counts を返す。"""
    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    resp = client.get("/api/dashboard/orchestra")
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data.get("sessions"), list)
    assert isinstance(data.get("handoffs"), list)
    counts = data.get("counts")
    assert isinstance(counts, dict)
    for key in ("sessions", "active_sessions", "agents", "handoffs", "pending_handoffs"):
        assert key in counts


def test_orchestra_includes_handoffs(tmp_path, monkeypatch):
    """承認待ち handoff が flywheel に出る。"""
    psm = server.PlatformStateManager(platform_home=tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: psm)

    from core.hierarchy.org_handoff import OrgHandoffStore

    store = OrgHandoffStore(platform_home=tmp_path)
    store.create(
        source_org="SNS運用",
        target_org="note販売",
        kind="audience_signal",
        title="バズ導線の引き渡し",
    )

    data = client.get("/api/dashboard/orchestra").json()
    titles = [h["title"] for h in data["handoffs"]]
    assert "バズ導線の引き渡し" in titles
    assert data["counts"]["handoffs"] >= 1
