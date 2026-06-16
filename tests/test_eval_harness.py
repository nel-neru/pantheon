"""Tests for C4a eval harness (deterministic via heuristic scoring / injected runner)."""

from __future__ import annotations

import yaml

from core.eval.harness import load_golden, run_suite

# A heuristic-strong output (len>100 + file:line + 改善 + bullet + no unresolved error) -> score 10.
_GOOD = "x" * 200 + " 改善提案 foo.py:1\n- item"


def _write_golden(d, **kw):
    (d / f"{kw['id']}.yaml").write_text(yaml.safe_dump(kw, allow_unicode=True), encoding="utf-8")


def test_load_golden_and_suite_filter(tmp_path):
    _write_golden(tmp_path, id="a", task_type="code_review", prompt="x", suite="agents")
    _write_golden(tmp_path, id="b", task_type="deep_research", prompt="y", suite="skills")
    assert {t.id for t in load_golden(golden_dir=tmp_path)} == {"a", "b"}
    assert [t.id for t in load_golden("agents", golden_dir=tmp_path)] == ["a"]


def test_run_suite_scores_and_emits_eval_span(tmp_path, monkeypatch):
    monkeypatch.setenv("PANTHEON_SPANS_LOG", str(tmp_path / "spans.jsonl"))
    _write_golden(tmp_path, id="good", task_type="code_review", prompt="x")
    summary = run_suite(golden_dir=tmp_path, runner=lambda t: _GOOD)  # llm=None -> heuristic
    assert summary["total"] == 1 and summary["passed"] == 1 and summary["pass_rate"] == 1.0
    assert summary["avg_score"] == 10.0

    from core.observability.span import TraceStore

    store = TraceStore()
    spans = [s for tr in store.recent_traces() for s in store.get_trace(tr.trace_id)]
    assert any(s.kind == "eval" for s in spans)


def test_expected_contains_gates_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("PANTHEON_SPANS_LOG", "off")
    _write_golden(tmp_path, id="c", task_type="t", prompt="x", expected_contains=["MUSTHAVE"])
    summary = run_suite(golden_dir=tmp_path, runner=lambda t: _GOOD)  # high score, missing token
    assert summary["total"] == 1 and summary["passed"] == 0  # contains gate fails


def test_runner_exception_is_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("PANTHEON_SPANS_LOG", "off")
    _write_golden(tmp_path, id="boom", task_type="t", prompt="x")

    def bad(_t):
        raise RuntimeError("boom")

    summary = run_suite(golden_dir=tmp_path, runner=bad)
    assert summary["total"] == 1 and summary["passed"] == 0  # empty output, no crash


def test_empty_golden_dir(tmp_path):
    assert run_suite(golden_dir=tmp_path)["total"] == 0
