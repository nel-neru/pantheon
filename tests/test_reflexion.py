"""Tests for C3 Reflexion: evaluate_llm + ReflexionLoop (LLM-judge with heuristic fallback)."""

from __future__ import annotations

import core.runtime.claude_code as cc
from core.intelligence.reflexion import ReflexionLoop
from core.intelligence.self_evaluator import AgentSelfEvaluator, EvaluationResult


class ScriptEvaluator(AgentSelfEvaluator):
    """Deterministic evaluator: score looked up by output string (retry if < 6)."""

    def __init__(self, scores: dict):
        self.scores = dict(scores)

    def evaluate_llm(self, output, task_type, *, llm=None):  # type: ignore[override]
        score = float(self.scores.get(output, 0.0))
        return EvaluationResult(score=score, feedback=f"fb:{output}", should_retry=score < 6.0)


# --------------------------- evaluate_llm --------------------------- #


def test_evaluate_llm_parses_score(monkeypatch):
    monkeypatch.setattr(cc, "claude_available", lambda: True)

    class FakeLLM:
        def complete(self, messages, **kw):
            assert kw.get("task_type") == "scoring"  # judge runs on the cheap tier
            return '{"score": 8, "feedback": "good"}'

    res = AgentSelfEvaluator().evaluate_llm("out", "t", llm=FakeLLM())
    assert res.score == 8.0 and res.should_retry is False and res.feedback == "good"


def test_evaluate_llm_falls_back_when_unavailable(monkeypatch):
    monkeypatch.setattr(cc, "claude_available", lambda: False)
    res = AgentSelfEvaluator().evaluate_llm("short", "t", llm=object())
    assert isinstance(res, EvaluationResult)  # heuristic shape preserved


def test_evaluate_llm_unparseable_falls_back(monkeypatch):
    monkeypatch.setattr(cc, "claude_available", lambda: True)

    class BadLLM:
        def complete(self, messages, **kw):
            return "not json at all"

    res = AgentSelfEvaluator().evaluate_llm("out", "t", llm=BadLLM())
    assert isinstance(res, EvaluationResult)


def test_evaluate_llm_none_llm_uses_heuristic():
    res = AgentSelfEvaluator().evaluate_llm("out", "t", llm=None)
    assert isinstance(res, EvaluationResult)


def test_parse_judge_handles_prose_and_garbage():
    ev = AgentSelfEvaluator()
    assert ev._parse_judge('{"score":5}')["score"] == 5
    assert ev._parse_judge('Sure! {"score": 7, "feedback":"ok"} done')["score"] == 7
    assert ev._parse_judge("garbage no json") is None


# --------------------------- ReflexionLoop --------------------------- #


def test_reflexion_skips_when_initial_good():
    ev = ScriptEvaluator({"v0": 9.0})
    calls = []

    def refine(prev, fb):
        calls.append(1)
        return "x"

    best, res, iters = ReflexionLoop(llm=object(), evaluator=ev).run(
        initial_output="v0", task_type="t", refine_fn=refine
    )
    assert iters == 0 and best == "v0" and not calls


def test_reflexion_improves():
    ev = ScriptEvaluator({"v0": 3.0, "v1": 8.0})
    best, res, iters = ReflexionLoop(llm=object(), max_iters=2, evaluator=ev).run(
        initial_output="v0", task_type="t", refine_fn=lambda p, f: "v1"
    )
    assert best == "v1" and res.score == 8.0 and iters == 1


def test_reflexion_caps_and_keeps_best():
    # refinement is always worse -> never adopted; loop stops at max_iters
    ev = ScriptEvaluator({"v0": 3.0, "bad": 1.0})
    best, res, iters = ReflexionLoop(llm=object(), max_iters=2, evaluator=ev).run(
        initial_output="v0", task_type="t", refine_fn=lambda p, f: "bad"
    )
    assert iters == 2 and best == "v0" and res.score == 3.0


def test_reflexion_refine_failure_keeps_best():
    ev = ScriptEvaluator({"v0": 3.0})

    def refine(prev, fb):
        raise RuntimeError("boom")

    best, res, iters = ReflexionLoop(llm=object(), max_iters=2, evaluator=ev).run(
        initial_output="v0", task_type="t", refine_fn=refine
    )
    assert best == "v0" and iters == 0


def test_reflexion_offline_uses_heuristic_deterministically():
    # llm=None -> evaluate_llm uses heuristic; a strong output scores high -> no retry.
    good = "x" * 200 + " 改善提案: foo.py:12 を修正\n- item"
    best, res, iters = ReflexionLoop(llm=None, max_iters=2).run(
        initial_output=good, task_type="t", refine_fn=lambda p, f: p
    )
    assert best == good and iters == 0


def test_reflexion_zero_max_iters_is_single_shot():
    ev = ScriptEvaluator({"v0": 1.0})  # would retry, but max_iters=0
    best, res, iters = ReflexionLoop(llm=object(), max_iters=0, evaluator=ev).run(
        initial_output="v0", task_type="t", refine_fn=lambda p, f: "v1"
    )
    assert iters == 0 and best == "v0"


# --------------------------- GenericSkillAgent._maybe_reflexion gate --------------------------- #


class CountingLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    def complete(self, messages, **kw):
        self.calls += 1
        return self.reply


def _agent(llm):
    from agents.generic_skill_agent import GenericSkillAgent

    return GenericSkillAgent.from_skills(["codebase_exploration", "deep_research"], llm_client=llm)


def test_maybe_reflexion_default_off_is_noop(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.delenv("PANTHEON_REFLEXION", raising=False)
    llm = CountingLLM("x")
    out = _agent(llm)._maybe_reflexion("INIT", SimpleNamespace(task_type="t"), [], llm, None)
    assert out == "INIT" and llm.calls == 0  # byte-identical, zero extra LLM calls


def test_maybe_reflexion_on_engages_and_adopts_improvement(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("PANTHEON_REFLEXION", "1")
    monkeypatch.setattr(cc, "claude_available", lambda: False)  # heuristic judge -> deterministic
    good = "x" * 200 + " 改善提案 foo.py:1\n- a"  # heuristic score 10 -> retry stops
    llm = CountingLLM(good)
    out = _agent(llm)._maybe_reflexion("INIT short", SimpleNamespace(task_type="t"), [], llm, None)
    assert llm.calls >= 1 and out == good
