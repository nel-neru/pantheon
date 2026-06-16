"""Tests for core.observability — spans + read-only TraceStore (C1)."""

from __future__ import annotations

import pytest

from core.observability import span as span_mod
from core.observability.span import (
    Span,
    TraceStore,
    record_llm_call,
    start_trace,
)


@pytest.fixture
def spans_log(tmp_path, monkeypatch):
    """Point the spans log at a temp file (override env, auto-cleaned by monkeypatch)."""
    path = tmp_path / "spans.jsonl"
    monkeypatch.setenv("PANTHEON_SPANS_LOG", str(path))
    return path


def test_span_roundtrip_drops_none_and_filters_unknown():
    span = Span(span_id="sp:1", trace_id="tr:1", kind="llm_call", name="x", model="fable")
    d = span.to_dict()
    assert "model" in d and d["model"] == "fable"
    assert "agent_id" not in d  # None fields dropped
    # from_dict ignores unknown keys (forward-compat)
    restored = Span.from_dict({**d, "future_field": 123})
    assert restored.span_id == "sp:1" and restored.model == "fable"


def test_trace_groups_and_rolls_up(spans_log):
    with start_trace("code_review", task_type="code_review", pattern="single"):
        record_llm_call(
            name="code_review",
            model="fable",
            elapsed_ms=10,
            task_type="code_review",
            input_tokens=100,
            output_tokens=20,
            total_cost_usd=0.01,
        )

    store = TraceStore()
    traces = store.recent_traces()
    assert len(traces) == 1
    t = traces[0]
    assert t.span_count == 2  # orchestration + llm_call
    assert t.task_type == "code_review"
    assert t.pattern == "single"
    assert t.input_tokens == 100 and t.output_tokens == 20
    assert t.total_cost_usd == 0.01
    assert t.status == "ok"


def test_llm_call_parents_to_trace_root(spans_log):
    with start_trace("task", task_type="t"):
        record_llm_call(name="t", model="haiku", elapsed_ms=5)

    store = TraceStore()
    trace_id = store.recent_traces()[0].trace_id
    spans = store.get_trace(trace_id)
    root = next(s for s in spans if s.parent_span_id is None)
    child = next(s for s in spans if s.kind == "llm_call")
    assert root.kind == "orchestration"
    assert child.parent_span_id == root.span_id
    assert child.trace_id == root.trace_id


def test_llm_call_without_trace_starts_singleton(spans_log):
    record_llm_call(name="solo", model="fable", elapsed_ms=3)
    traces = TraceStore().recent_traces()
    assert len(traces) == 1
    spans = TraceStore().get_trace(traces[0].trace_id)
    assert len(spans) == 1 and spans[0].parent_span_id is None


def test_error_status_propagates_to_trace(spans_log):
    with start_trace("task"):
        record_llm_call(name="t", model="fable", elapsed_ms=1, status="error")
    assert TraceStore().recent_traces()[0].status == "error"


def test_write_failure_never_raises(spans_log, monkeypatch):
    def boom(_record):
        raise OSError("disk full")

    monkeypatch.setattr(span_mod, "write_span", boom)
    # Neither path may propagate the error.
    with start_trace("task"):
        record_llm_call(name="t", model="fable", elapsed_ms=1)
    # store reads an (empty) file — no spans written, no crash
    assert TraceStore().recent_traces() == []


def test_emit_llm_span_from_claude_code(spans_log):
    from core.runtime.claude_code import _emit_llm_span

    _emit_llm_span(
        elapsed_ms=42,
        model="fable",
        task_type="security_audit",
        returncode=1,  # nonzero -> error status
        timed_out=False,
        usage={"input_tokens": 5, "output_tokens": 2},
        total_cost_usd=0.002,
    )
    traces = TraceStore().recent_traces()
    assert len(traces) == 1
    spans = TraceStore().get_trace(traces[0].trace_id)
    assert spans[0].kind == "llm_call"
    assert spans[0].status == "error"
    assert spans[0].task_type == "security_audit"


def test_disabled_env_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("PANTHEON_SPANS_LOG", "off")
    with start_trace("task"):
        record_llm_call(name="t", model="fable", elapsed_ms=1)
    assert TraceStore().recent_traces() == []
