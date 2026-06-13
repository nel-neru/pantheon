"""Tests for core.trends.business_proposal（P2.1 trend → 新規事業提案）。

純粋関数なので I/O も tmp_path も不要。決定論・冪等・閾値・genre 推定を検証する。
"""

from __future__ import annotations

import pytest

from core.trends.business_proposal import (
    BUSINESS_PROPOSAL_MIN_SCORE,
    is_business_worthy,
    trend_to_business_proposal,
)


def test_high_score_trend_converts_to_business_proposal():
    trend = {
        "title": "AI 副業の自動化",
        "score": 0.92,
        "genre": "side_business",
        "summary": "個人開発者が AI で月次収益を伸ばしている事例が急増",
        "url": "https://example.com/ai-side-business",
    }
    proposal = trend_to_business_proposal(trend)

    assert proposal["kind"] == "new_business"
    assert proposal["genre"] == "side_business"
    assert proposal["name"] == "side_business 事業"
    assert proposal["source_trend"] == "AI 副業の自動化"
    assert proposal["requires_human_gate"] is True
    # 非動画系は集客＋収益化の 2 部門
    assert proposal["suggested_divisions"] == ["audience_development", "monetization"]
    # rationale は判断材料（score と summary）を含む
    assert "0.92" in proposal["rationale"]
    assert "月次収益" in proposal["rationale"]


def test_video_genre_gets_content_production_division():
    trend = {
        "title": "ショート動画編集の自動化",
        "score": 0.81,
        "genre": "video_edit",
        "summary": "動画編集 SaaS が伸びている",
    }
    proposal = trend_to_business_proposal(trend)

    assert proposal["genre"] == "video_edit"
    # 動画系は制作部門を含む 3 部門
    assert proposal["suggested_divisions"] == [
        "audience_development",
        "content_production",
        "monetization",
    ]


def test_genre_inferred_from_title_when_missing():
    trend = {
        "title": "Notion テンプレート販売",
        "score": 0.7,
        "summary": "テンプレ販売が好調",
    }
    proposal = trend_to_business_proposal(trend)

    # genre 省略時は title から slug 推定される（小文字・先頭語を _ 連結）
    assert proposal["genre"]
    assert proposal["genre"] != "general"
    assert proposal["genre"] == proposal["genre"].lower()
    assert " " not in proposal["genre"]
    assert proposal["name"] == f"{proposal['genre']} 事業"


def test_low_score_is_not_business_worthy():
    trend = {"title": "微妙なネタ", "score": 0.3}
    assert is_business_worthy(trend) is False


def test_low_score_conversion_raises_value_error():
    trend = {"title": "微妙なネタ", "score": 0.3}
    with pytest.raises(ValueError):
        trend_to_business_proposal(trend)


def test_threshold_boundary_is_inclusive():
    # ちょうど閾値（0.6）は worthy（>=）
    at_threshold = {"title": "境界ネタ", "score": BUSINESS_PROPOSAL_MIN_SCORE}
    just_below = {"title": "境界下", "score": BUSINESS_PROPOSAL_MIN_SCORE - 0.01}

    assert is_business_worthy(at_threshold) is True
    assert is_business_worthy(just_below) is False
    # 境界ちょうどは変換できる（例外を投げない）
    assert trend_to_business_proposal(at_threshold)["kind"] == "new_business"


def test_missing_or_invalid_score_treated_as_zero():
    assert is_business_worthy({"title": "スコア無し"}) is False
    assert is_business_worthy({"title": "不正", "score": "not-a-number"}) is False


def test_conversion_is_deterministic_and_idempotent():
    trend = {
        "title": "AI 副業の自動化",
        "score": 0.92,
        "genre": "side_business",
        "summary": "急増",
        "url": "https://example.com/x",
    }
    first = trend_to_business_proposal(trend)
    second = trend_to_business_proposal(dict(trend))
    assert first == second


def test_summary_optional_does_not_break_rationale():
    trend = {"title": "要約なし事業", "score": 0.75, "genre": "saas"}
    proposal = trend_to_business_proposal(trend)
    # summary が無くても score は rationale に含まれる
    assert "0.75" in proposal["rationale"]
