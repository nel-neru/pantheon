"""Tests for LLM token usage tracking (core/llm/usage.py + /api/usage)."""

from __future__ import annotations

from fastapi.testclient import TestClient

import web.server as server
from core.llm.usage import UsageTracker, get_usage_tracker, record_usage, reset_usage

client = TestClient(server.app)


def test_tracker_records_and_aggregates():
    tracker = UsageTracker()
    tracker.record("openai", "gpt-4o", {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
    tracker.record("openai", "gpt-4o", {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5})
    tracker.record("anthropic", "claude-sonnet-4-5", {"prompt_tokens": 100, "completion_tokens": 50})

    snap = tracker.snapshot()
    assert snap["totals"] == {"calls": 3, "prompt_tokens": 112, "completion_tokens": 58, "total_tokens": 170}
    assert snap["by_provider"]["openai"]["total_tokens"] == 20
    assert snap["by_provider"]["anthropic"]["total_tokens"] == 150  # total derived from prompt+completion
    by_model = {(r["provider"], r["model"]): r for r in snap["by_model"]}
    assert by_model[("openai", "gpt-4o")]["calls"] == 2


def test_record_with_no_usage_counts_calls_only():
    tracker = UsageTracker()
    tracker.record("groq", "llama-3.1-70b-versatile", None)
    snap = tracker.snapshot()
    assert snap["totals"]["calls"] == 1
    assert snap["totals"]["total_tokens"] == 0


def test_record_usage_is_best_effort_and_uses_singleton():
    reset_usage()
    record_usage("gemini", "gemini-2.0-flash", {"prompt_tokens": 7, "completion_tokens": 1, "total_tokens": 8})
    # 不正な usage でも例外を出さない
    record_usage("gemini", "gemini-2.0-flash", "not-a-dict")  # type: ignore[arg-type]
    snap = get_usage_tracker().snapshot()
    assert snap["by_provider"]["gemini"]["prompt_tokens"] == 7


def test_usage_api_endpoint_and_reset():
    reset_usage()
    get_usage_tracker().record("openai", "gpt-4o", {"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 10})

    response = client.get("/api/usage")
    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["total_tokens"] == 10
    assert "by_model" in body and "by_provider" in body

    deleted = client.delete("/api/usage")
    assert deleted.status_code == 200
    assert client.get("/api/usage").json()["totals"]["total_tokens"] == 0
