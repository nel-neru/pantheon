"""core/trends/trend_dedup.py の純粋関数テスト（tmp_path 不要）。"""

from __future__ import annotations

import copy

from core.trends.models import TrendItem
from core.trends.runner import _dedupe_items
from core.trends.trend_dedup import _normalize_key, dedupe_trends, rank_trends


def test_runner_dedupe_items_collapses_url_variants_keeping_highest_score() -> None:
    """P2.5: 収集パイプラインの _dedupe_items が url 正規化で near-dup を最高スコア1件に畳む。"""
    items = [
        TrendItem(source="web", url="https://ex.com/a/", title="A low", score=4.0, genre="ai"),
        TrendItem(source="youtube", url="https://EX.com/a", title="A high", score=9.0, genre="ai"),
        TrendItem(source="web", url="https://ex.com/b", title="B", score=7.0, genre="ai"),
    ]
    out = _dedupe_items(items)
    assert len(out) == 2  # /a/ と /A は同一キーへ集約
    survivor = next(i for i in out if "/a" in i.url.lower())
    assert survivor.score == 9.0  # 高スコア側が残る


def test_normalize_key_uses_url_lowercased_and_trailing_slash_stripped() -> None:
    assert _normalize_key({"url": "https://Example.com/Post/"}) == "https://example.com/post"
    assert _normalize_key({"url": "  https://EXAMPLE.com/a  "}) == "https://example.com/a"


def test_normalize_key_falls_back_to_title_when_url_missing_or_empty() -> None:
    assert _normalize_key({"title": "  Hello   World  "}) == "hello world"
    # 空文字列の url はフォールバックして title を使う
    assert _normalize_key({"url": "", "title": "Foo Bar"}) == "foo bar"


def test_normalize_key_empty_when_no_url_or_title() -> None:
    assert _normalize_key({}) == ""


def test_dedupe_by_url_keeps_highest_score() -> None:
    trends = [
        {"url": "https://a.com/x", "title": "low", "score": 1.0},
        {"url": "https://A.com/x/", "title": "high", "score": 9.0},
        {"url": "https://a.com/x", "title": "mid", "score": 5.0},
    ]
    result = dedupe_trends(trends)
    assert len(result) == 1
    assert result[0]["title"] == "high"


def test_dedupe_by_title_when_url_absent() -> None:
    trends = [
        {"title": "Same Topic", "score": 2.0},
        {"title": "same   topic", "score": 7.0},
    ]
    result = dedupe_trends(trends)
    assert len(result) == 1
    assert result[0]["score"] == 7.0


def test_dedupe_missing_score_treated_as_zero() -> None:
    trends = [
        {"url": "https://a.com", "title": "no-score"},
        {"url": "https://a.com", "title": "scored", "score": 3.0},
    ]
    result = dedupe_trends(trends)
    assert len(result) == 1
    assert result[0]["title"] == "scored"


def test_dedupe_preserves_first_occurrence_order_stable() -> None:
    trends = [
        {"url": "https://b.com", "score": 1.0},
        {"url": "https://a.com", "score": 1.0},
        {"url": "https://b.com", "score": 1.0},
    ]
    result = dedupe_trends(trends)
    assert [t["url"] for t in result] == ["https://b.com", "https://a.com"]


def test_dedupe_tie_score_keeps_earlier() -> None:
    trends = [
        {"url": "https://a.com", "title": "first", "score": 4.0},
        {"url": "https://a.com", "title": "second", "score": 4.0},
    ]
    result = dedupe_trends(trends)
    assert result[0]["title"] == "first"


def test_dedupe_empty_input() -> None:
    assert dedupe_trends([]) == []


def test_dedupe_does_not_mutate_input() -> None:
    trends = [
        {"url": "https://a.com", "score": 1.0},
        {"url": "https://a.com", "score": 5.0},
    ]
    snapshot = copy.deepcopy(trends)
    dedupe_trends(trends)
    assert trends == snapshot


def test_rank_orders_by_score_descending() -> None:
    trends = [
        {"url": "https://a.com", "score": 2.0},
        {"url": "https://b.com", "score": 8.0},
        {"url": "https://c.com", "score": 5.0},
    ]
    result = rank_trends(trends)
    assert [t["url"] for t in result] == [
        "https://b.com",
        "https://c.com",
        "https://a.com",
    ]


def test_rank_tie_score_is_stable_by_input_order() -> None:
    trends = [
        {"url": "https://x.com", "title": "x", "score": 5.0},
        {"url": "https://y.com", "title": "y", "score": 5.0},
        {"url": "https://z.com", "title": "z", "score": 5.0},
    ]
    result = rank_trends(trends)
    assert [t["title"] for t in result] == ["x", "y", "z"]


def test_rank_applies_min_score_filter() -> None:
    trends = [
        {"url": "https://a.com", "score": 1.0},
        {"url": "https://b.com", "score": 6.0},
        {"url": "https://c.com", "score": 3.0},
    ]
    result = rank_trends(trends, min_score=3.0)
    assert [t["url"] for t in result] == ["https://b.com", "https://c.com"]


def test_rank_applies_limit() -> None:
    trends = [
        {"url": "https://a.com", "score": 1.0},
        {"url": "https://b.com", "score": 6.0},
        {"url": "https://c.com", "score": 3.0},
    ]
    result = rank_trends(trends, limit=2)
    assert [t["url"] for t in result] == ["https://b.com", "https://c.com"]


def test_rank_limit_zero_returns_empty() -> None:
    trends = [{"url": "https://a.com", "score": 1.0}]
    assert rank_trends(trends, limit=0) == []


def test_rank_dedupes_before_ranking() -> None:
    trends = [
        {"url": "https://a.com", "title": "low", "score": 1.0},
        {"url": "https://a.com", "title": "high", "score": 9.0},
        {"url": "https://b.com", "title": "mid", "score": 5.0},
    ]
    result = rank_trends(trends)
    assert [t["title"] for t in result] == ["high", "mid"]


def test_rank_missing_score_treated_as_zero_and_filtered() -> None:
    trends = [
        {"url": "https://a.com", "title": "no-score"},
        {"url": "https://b.com", "title": "scored", "score": 2.0},
    ]
    result = rank_trends(trends, min_score=1.0)
    assert [t["title"] for t in result] == ["scored"]


def test_rank_empty_input() -> None:
    assert rank_trends([]) == []


def test_rank_does_not_mutate_input() -> None:
    trends = [
        {"url": "https://a.com", "score": 2.0},
        {"url": "https://a.com", "score": 8.0},
        {"url": "https://b.com", "score": 5.0},
    ]
    snapshot = copy.deepcopy(trends)
    rank_trends(trends, min_score=1.0, limit=5)
    assert trends == snapshot


def test_rank_is_idempotent_on_already_ranked_dicts() -> None:
    trends = [
        {"url": "https://a.com", "score": 9.0},
        {"url": "https://b.com", "score": 5.0},
        {"url": "https://c.com", "score": 1.0},
    ]
    once = rank_trends(trends)
    twice = rank_trends(once)
    assert once == twice
