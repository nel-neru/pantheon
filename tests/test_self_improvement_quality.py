from __future__ import annotations

from types import SimpleNamespace

from core.quality.self_improvement_loop import SelfImprovementLoop


def test_quality_from_result_prefers_output_scores():
    q = SelfImprovementLoop._quality_from_result
    assert q(SimpleNamespace(output={"quality_score": 7.5}, success=True)) == 7.5
    assert q(SimpleNamespace(output={"review_score": 6}, success=False)) == 6.0
    assert q(SimpleNamespace(output={"overall_score": 9}, success=True)) == 9.0


def test_quality_from_result_falls_back_to_success_flag():
    q = SelfImprovementLoop._quality_from_result
    assert q(SimpleNamespace(output="done", success=True)) == 8.0
    assert q(SimpleNamespace(output=None, success=False)) == 2.0
    assert q(SimpleNamespace(output={"foo": "bar"}, success=True)) == 8.0
    assert q(SimpleNamespace()) == 2.0
