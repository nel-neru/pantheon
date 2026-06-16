"""Tests for C4a read-only observability API endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    monkeypatch.setenv("PANTHEON_SPANS_LOG", str(tmp_path / "spans.jsonl"))
    from web.server import app

    return TestClient(app)


def test_observability_summary_and_traces(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    from core.observability.span import record_llm_call

    record_llm_call(
        name="code_review",
        model="fable",
        elapsed_ms=5,
        input_tokens=10,
        output_tokens=2,
        total_cost_usd=0.01,
    )

    r = client.get("/api/observability/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["trace_count"] >= 1 and "traces" in body

    r2 = client.get("/api/observability/traces")
    assert r2.status_code == 200
    traces = r2.json()["traces"]
    assert isinstance(traces, list) and traces
    tid = traces[0]["trace_id"]

    r3 = client.get("/api/observability/traces", params={"trace_id": tid})
    assert r3.status_code == 200
    spans = r3.json()["spans"]
    assert any(s["kind"] == "llm_call" for s in spans)


def test_observability_summary_empty_is_ok(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.get("/api/observability/summary")
    assert r.status_code == 200 and r.json()["trace_count"] == 0
