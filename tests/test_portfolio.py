"""core/metrics/portfolio.recommend_allocation の決定論テスト。

純粋関数なので get_platform_home / tmp_path には依存しない。
4 アクション全網羅・空入力・並び順を検証する。
"""

from __future__ import annotations

from core.metrics.portfolio import recommend_allocation


def _by_name(rows):
    return {row["org_name"]: row for row in rows}


def test_empty_input_returns_empty_list():
    assert recommend_allocation([]) == []


def test_all_four_actions_emitted():
    # high: 収益あり・高 ROI → invest
    # low:  収益あり・低 ROI → optimize
    # reach_only: リーチのみ・収益0 → monetize
    # cold: リーチも収益も0 → grow_audience
    stats = [
        {"org_name": "high", "revenue": 1000.0, "reach": 1000.0, "posts": 10.0},
        {"org_name": "low", "revenue": 100.0, "reach": 100000.0, "posts": 50.0},
        {"org_name": "reach_only", "revenue": 0.0, "reach": 5000.0, "posts": 20.0},
        {"org_name": "cold", "revenue": 0.0, "reach": 0.0, "posts": 0.0},
    ]
    result = recommend_allocation(stats)
    actions = {row["org_name"]: row["action"] for row in result}
    assert actions["high"] == "invest"
    assert actions["low"] == "optimize"
    assert actions["reach_only"] == "monetize"
    assert actions["cold"] == "grow_audience"
    # 全 org に必須キーが揃う
    for row in result:
        assert set(row) == {"org_name", "action", "roi", "reason"}
        assert isinstance(row["roi"], float)
        assert row["reason"]


def test_roi_uses_no_zero_division():
    # reach=0 かつ revenue>0 でもゼロ除算せず ROI = revenue/1 = revenue。
    stats = [{"org_name": "a", "revenue": 42.0, "reach": 0.0, "posts": 1.0}]
    result = recommend_allocation(stats)
    assert result[0]["roi"] == 42.0
    # 単独 org は ROI が中央値そのもの（>=）なので invest。
    assert result[0]["action"] == "invest"


def test_ordering_by_action_priority_then_revenue_desc():
    # action 優先度 invest -> monetize -> optimize -> grow_audience の順、
    # 同一 action 内は revenue 降順で並ぶこと。
    stats = [
        # invest 群（高 ROI）: revenue 降順で invest_big -> invest_small
        {"org_name": "invest_small", "revenue": 500.0, "reach": 100.0, "posts": 5.0},
        {"org_name": "invest_big", "revenue": 2000.0, "reach": 100.0, "posts": 5.0},
        # monetize 群: revenue 0、revenue 降順は同値なので reach 影響なく安定
        {"org_name": "monetize_a", "revenue": 0.0, "reach": 3000.0, "posts": 9.0},
        # optimize 群（低 ROI）
        {"org_name": "optimize_a", "revenue": 50.0, "reach": 500000.0, "posts": 99.0},
        # grow_audience 群
        {"org_name": "cold_a", "revenue": 0.0, "reach": 0.0, "posts": 0.0},
    ]
    result = recommend_allocation(stats)
    order = [row["org_name"] for row in result]
    actions = [row["action"] for row in result]

    # action の優先度が単調非減少であること
    priority = {"invest": 0, "monetize": 1, "optimize": 2, "grow_audience": 3}
    ranks = [priority[a] for a in actions]
    assert ranks == sorted(ranks)

    # invest 群が先頭に来て、その中で revenue 降順
    assert order[0] == "invest_big"
    assert order[1] == "invest_small"
    # grow_audience が末尾
    assert order[-1] == "cold_a"
    # 各 action がちょうど期待位置に出ている
    by_name = _by_name(result)
    assert by_name["monetize_a"]["action"] == "monetize"
    assert by_name["optimize_a"]["action"] == "optimize"


def test_deterministic_idempotent():
    stats = [
        {"org_name": "x", "revenue": 100.0, "reach": 200.0, "posts": 3.0},
        {"org_name": "y", "revenue": 0.0, "reach": 800.0, "posts": 7.0},
    ]
    first = recommend_allocation(stats)
    second = recommend_allocation(stats)
    assert first == second
    # 入力辞書は破壊されない
    assert stats[0] == {"org_name": "x", "revenue": 100.0, "reach": 200.0, "posts": 3.0}
