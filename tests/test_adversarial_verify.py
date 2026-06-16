"""Tests for C4: PARALLEL_FINDERS_VERIFY pattern + review-loop/parallel improvements."""

from __future__ import annotations

from types import SimpleNamespace

from core.intelligence.capability_registry import CapabilityRegistry
from core.orchestration.pre_task_orchestrator import OrchestrationPattern, PreTaskOrchestrator


def _task():
    return SimpleNamespace(input={"k": "v"}, task_type="security_audit", description="audit")


def _analysis(ids):
    return SimpleNamespace(
        recommended_agent_ids=ids,
        task_type="security_audit",
        recommended_pattern=OrchestrationPattern.PARALLEL_FINDERS_VERIFY,
    )


def _factory(d):
    return lambda aid: d.get(aid)


class Stub:
    def __init__(self, output, success=True):
        self._o = output
        self._s = success

    async def run(self, task):
        return SimpleNamespace(success=self._s, output=self._o)


class StubFailOnVerify:
    """Succeeds as a finder, raises when used as the verifier (task_type='verify')."""

    def __init__(self, output):
        self._o = output

    async def run(self, task):
        if getattr(task, "task_type", "") == "verify":
            raise RuntimeError("verify boom")
        return SimpleNamespace(success=True, output=self._o)


# --------------------------- adversarial verify --------------------------- #


async def test_adversarial_verify_synthesizes_and_scores():
    orch = PreTaskOrchestrator()
    f1 = Stub({"finding": "a"})
    f2 = Stub({"finding": "b", "verified": True})  # last finder doubles as verifier
    res = await orch._execute_adversarial_verify(
        _task(), _analysis(["f1", "f2"]), _factory({"f1": f1, "f2": f2})
    )
    assert res.success
    assert res.output["verified"] is True
    assert res.output["finder_count"] == 2
    assert res.output["findings"] == [{"finding": "a"}, {"finding": "b", "verified": True}]
    assert isinstance(orch._last_quality_score, float)  # real quality recorded (not default)


async def test_adversarial_verify_keeps_findings_when_verifier_fails():
    orch = PreTaskOrchestrator()
    v = StubFailOnVerify({"f": "x"})
    res = await orch._execute_adversarial_verify(_task(), _analysis(["v"]), _factory({"v": v}))
    assert res.success and res.output["verified"] is False
    assert res.output["findings"] == [{"f": "x"}]


async def test_adversarial_verify_all_finders_fail():
    orch = PreTaskOrchestrator()
    bad = Stub(None, success=False)
    res = await orch._execute_adversarial_verify(_task(), _analysis(["b"]), _factory({"b": bad}))
    assert res.success is False


async def test_adversarial_verify_no_agents():
    orch = PreTaskOrchestrator()
    res = await orch._execute_adversarial_verify(_task(), _analysis([]), _factory({}))
    assert res.success is False


async def test_execute_dispatches_to_adversarial_verify(monkeypatch):
    monkeypatch.setenv("PANTHEON_SPANS_LOG", "off")  # isolate observability
    orch = PreTaskOrchestrator()
    f = Stub({"finding": "x"})
    res = await orch.execute(_task(), _analysis(["f"]), _factory({"f": f}), record=False)
    assert "findings" in res.output and res.output["finder_count"] == 1


# --------------------------- review-loop consumes reviewer --------------------------- #


async def test_review_loop_attaches_reviewer_output():
    orch = PreTaskOrchestrator()
    main = Stub({"who": "main"})
    rev = Stub({"who": "rev"})
    res = await orch._execute_review_loop(
        _task(), SimpleNamespace(recommended_agent_ids=["m", "r"]), _factory({"m": main, "r": rev})
    )
    assert res.output["who"] == "main"  # unchanged contract
    assert res.output["review"] == {"who": "rev"}  # reviewer no longer discarded


# --------------------------- parallel merges outputs --------------------------- #


async def test_parallel_merges_successful_outputs():
    orch = PreTaskOrchestrator()
    a = Stub({"who": "a"})
    b = Stub({"who": "b"})
    res = await orch._execute_parallel(
        _task(), SimpleNamespace(recommended_agent_ids=["a", "b"]), _factory({"a": a, "b": b})
    )
    assert res.output["who"] == "a"  # first success is the representative
    assert res.output["_merged_outputs"] == [{"who": "b"}]  # the other agents' outputs


# --------------------------- analyze() env opt-in --------------------------- #


def test_analyze_opt_in_upgrades_security_audit(monkeypatch, tmp_path):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    monkeypatch.setenv("PANTHEON_ADVERSARIAL_VERIFY", "1")
    orch = PreTaskOrchestrator(capability_registry=CapabilityRegistry(platform_home=tmp_path))
    analysis = orch.analyze("security_audit", "監査する")
    assert analysis.recommended_pattern == OrchestrationPattern.PARALLEL_FINDERS_VERIFY


def test_analyze_default_keeps_review_loop(monkeypatch, tmp_path):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    monkeypatch.delenv("PANTHEON_ADVERSARIAL_VERIFY", raising=False)
    orch = PreTaskOrchestrator(capability_registry=CapabilityRegistry(platform_home=tmp_path))
    analysis = orch.analyze("security_audit", "監査する")
    assert analysis.recommended_pattern == OrchestrationPattern.REVIEW_LOOP
