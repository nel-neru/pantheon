"""``core.hierarchy.handoff_optimizer.recommend_handoffs`` の決定論ロジックを検証する。"""

from __future__ import annotations

from core.hierarchy.handoff_optimizer import recommend_handoffs


def test_recommends_audience_to_monetization() -> None:
    # 集客 org（収益弱）→ 収益化 org の推奨が 1 件出る。
    stats = [
        {"org_name": "sns", "reach": 10000, "revenue": 0, "role": "audience"},
        {"org_name": "affiliate", "reach": 100, "revenue": 500, "role": "monetization"},
    ]
    recs = recommend_handoffs(stats)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["from_org"] == "sns"
    assert rec["to_org"] == "affiliate"
    assert set(rec.keys()) == {"from_org", "to_org", "reason", "priority"}
    assert isinstance(rec["reason"], str) and rec["reason"]
    assert rec["priority"] == 10000


def test_empty_when_no_monetization_org() -> None:
    # 収益化 org が存在しなければ推奨は空。
    stats = [
        {"org_name": "sns", "reach": 10000, "revenue": 0, "role": "audience"},
        {"org_name": "note", "reach": 5000, "revenue": 0, "role": "audience"},
    ]
    assert recommend_handoffs(stats) == []


def test_empty_when_no_audience_org() -> None:
    # 集客 org が存在しなければ推奨は空。
    stats = [
        {"org_name": "affiliate", "reach": 100, "revenue": 500, "role": "monetization"},
    ]
    assert recommend_handoffs(stats) == []


def test_empty_input_returns_empty() -> None:
    assert recommend_handoffs([]) == []


def test_role_inference_from_reach_and_revenue() -> None:
    # role 未指定でも reach>0 & revenue<=0 → audience、revenue>0 → monetization と推定。
    stats = [
        {"org_name": "reach_only", "reach": 8000, "revenue": 0},
        {"org_name": "earner", "reach": 50, "revenue": 1200},
    ]
    recs = recommend_handoffs(stats)
    assert len(recs) == 1
    assert recs[0]["from_org"] == "reach_only"
    assert recs[0]["to_org"] == "earner"


def test_explicit_role_overrides_inference() -> None:
    # 明示 role は推定より優先。revenue>0 でも role=audience なら集客側に分類される。
    stats = [
        {"org_name": "hybrid", "reach": 9000, "revenue": 300, "role": "audience"},
        {"org_name": "shop", "reach": 10, "revenue": 200, "role": "monetization"},
    ]
    recs = recommend_handoffs(stats)
    assert len(recs) == 1
    assert recs[0]["from_org"] == "hybrid"
    assert recs[0]["to_org"] == "shop"


def test_orders_by_reach_descending() -> None:
    # 複数の audience は reach 降順で並ぶ。
    stats = [
        {"org_name": "small", "reach": 1000, "revenue": 0, "role": "audience"},
        {"org_name": "big", "reach": 50000, "revenue": 0, "role": "audience"},
        {"org_name": "mid", "reach": 8000, "revenue": 0, "role": "audience"},
        {"org_name": "shop", "reach": 10, "revenue": 900, "role": "monetization"},
    ]
    recs = recommend_handoffs(stats)
    assert [r["from_org"] for r in recs] == ["big", "mid", "small"]
    assert all(r["to_org"] == "shop" for r in recs)


def test_picks_highest_revenue_monetization_target() -> None:
    # 収益化 org が複数あるときは最も revenue の高いものを宛先にする。
    stats = [
        {"org_name": "sns", "reach": 12000, "revenue": 0, "role": "audience"},
        {"org_name": "low_earner", "reach": 30, "revenue": 100, "role": "monetization"},
        {"org_name": "high_earner", "reach": 40, "revenue": 5000, "role": "monetization"},
    ]
    recs = recommend_handoffs(stats)
    assert len(recs) == 1
    assert recs[0]["to_org"] == "high_earner"


def test_deterministic_and_idempotent() -> None:
    # 同一入力で繰り返し呼んでも同一結果（純粋関数）。
    stats = [
        {"org_name": "a", "reach": 3000, "revenue": 0, "role": "audience"},
        {"org_name": "b", "reach": 3000, "revenue": 0, "role": "audience"},
        {"org_name": "m", "reach": 5, "revenue": 700, "role": "monetization"},
    ]
    first = recommend_handoffs(stats)
    second = recommend_handoffs(stats)
    assert first == second
    # 同 reach は入力順で安定。
    assert [r["from_org"] for r in first] == ["a", "b"]


def test_handles_missing_and_invalid_numeric_fields() -> None:
    # reach/revenue 欠落・非数値でも例外を投げず 0 扱い（ゼロ除算なし）。
    stats = [
        {"org_name": "noisy", "reach": "abc", "role": "audience"},
        {"org_name": "clean", "reach": 4000, "revenue": 0, "role": "audience"},
        {"org_name": "earner", "revenue": 250, "role": "monetization"},
    ]
    recs = recommend_handoffs(stats)
    # reach=0 と扱われる noisy より reach=4000 の clean が先。
    assert [r["from_org"] for r in recs] == ["clean", "noisy"]
    assert all(r["to_org"] == "earner" for r in recs)
