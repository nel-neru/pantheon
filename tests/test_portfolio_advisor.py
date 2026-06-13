"""build_portfolio_proposals のテスト（純粋関数 — tmp_path 不要）。

検証点:
- 配分提案と連携提案の両方が出ること。
- kind / title / priority / action の整合。
- 空入力 → []。
- priority 降順の並び順。
- 冪等性（同じ入力を 2 回呼んでも同一結果）。
- source_org_name の注入。
- 入力辞書を破壊しないこと。
"""

from __future__ import annotations

from typing import Any, Dict, List

from core.hierarchy.portfolio_advisor import build_portfolio_proposals


def _sample_stats() -> List[Dict[str, Any]]:
    """配分と連携の両方が生まれるように設計したサンプル。

    - alpha: 収益高・ROI 高 → invest、かつ monetization 宛先。
    - beta : reach あり・収益 0 → monetize、かつ audience 送元。
    - gamma: reach あり・収益 0（beta より reach 大）→ monetize、audience 送元。
    """
    return [
        {"org_name": "alpha", "revenue": 1000.0, "reach": 1000.0, "posts": 10.0},
        {"org_name": "beta", "revenue": 0.0, "reach": 500.0, "posts": 5.0},
        {"org_name": "gamma", "revenue": 0.0, "reach": 800.0, "posts": 8.0},
    ]


def test_empty_input_returns_empty() -> None:
    assert build_portfolio_proposals([]) == []


def test_produces_both_kinds() -> None:
    proposals = build_portfolio_proposals(_sample_stats())
    kinds = {p["kind"] for p in proposals}
    assert "portfolio_allocation" in kinds
    assert "handoff" in kinds


def test_allocation_proposal_shape_and_priority() -> None:
    proposals = build_portfolio_proposals(_sample_stats())
    allocations = [p for p in proposals if p["kind"] == "portfolio_allocation"]
    # 各 org に 1 件ずつ出る。
    assert {p["org_name"] for p in allocations} == {"alpha", "beta", "gamma"}

    by_org = {p["org_name"]: p for p in allocations}
    alpha = by_org["alpha"]
    assert alpha["action"] == "invest"
    assert alpha["priority"] == 3
    assert alpha["title"] == "[HQ提案] alpha を invest"
    assert alpha["source_org_name"] == "HQ"
    assert alpha["reason"]  # 理由が入っている。

    # reach あり・収益 0 は monetize → priority 2。
    assert by_org["beta"]["action"] == "monetize"
    assert by_org["beta"]["priority"] == 2
    assert by_org["gamma"]["action"] == "monetize"
    assert by_org["gamma"]["priority"] == 2


def test_handoff_proposal_shape_and_priority() -> None:
    proposals = build_portfolio_proposals(_sample_stats())
    handoffs = [p for p in proposals if p["kind"] == "handoff"]
    assert handoffs, "連携提案が少なくとも 1 件出るはず"

    for h in handoffs:
        # 宛先は唯一の monetization org alpha。送元は audience。
        assert h["to_org"] == "alpha"
        assert h["from_org"] in {"beta", "gamma"}
        assert h["title"] == f"[HQ提案] {h['from_org']}→{h['to_org']} へ送客"
        assert h["source_org_name"] == "HQ"
        assert isinstance(h["priority"], int)
        assert h["reason"]

    # gamma（reach 800）の priority > beta（reach 500）の priority。
    pri = {h["from_org"]: h["priority"] for h in handoffs}
    assert pri["gamma"] == 800
    assert pri["beta"] == 500
    assert pri["gamma"] > pri["beta"]


def test_sorted_by_priority_descending() -> None:
    proposals = build_portfolio_proposals(_sample_stats())
    priorities = [p["priority"] for p in proposals]
    assert priorities == sorted(priorities, reverse=True)
    # 先頭は最高 priority の連携（gamma→alpha, priority=800）。
    assert proposals[0]["priority"] == 800


def test_deterministic_and_idempotent() -> None:
    stats = _sample_stats()
    first = build_portfolio_proposals(stats)
    second = build_portfolio_proposals(stats)
    assert first == second


def test_custom_source_org_name_is_injected() -> None:
    proposals = build_portfolio_proposals(_sample_stats(), source_org_name="Pantheon-HQ")
    assert proposals  # 提案が出ている。
    assert all(p["source_org_name"] == "Pantheon-HQ" for p in proposals)


def test_input_not_mutated() -> None:
    stats = _sample_stats()
    import copy

    snapshot = copy.deepcopy(stats)
    build_portfolio_proposals(stats)
    assert stats == snapshot
