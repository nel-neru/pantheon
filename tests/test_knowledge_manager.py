"""Unit tests for KnowledgeManager"""

import json

import pytest

from core.knowledge.manager import KnowledgeManager


@pytest.fixture
def km(tmp_path):
    return KnowledgeManager(tmp_path)


def test_sort_methods_tolerate_null_created_at_and_usage_count(tmp_path):
    """created_at/usage_count が null の生 JSON 知識レコード（legacy/手編集）で各並べ替えが落ちない。

    回帰: 知識取得の各経路のソートキーが
    - ``record.get("created_at", "")`` → null で ``None < str`` TypeError（_load_all_entries 全経路）
    - ``-int(record.get("usage_count", 0))`` → null で ``int(None)`` TypeError
      （get_by_importance / get_best_practices / get_for_repo）
    を起こし、知識取得全体を落としていた。
    """
    km = KnowledgeManager(tmp_path)
    km.save_insight(
        "ok", "valid entry", tags=["repo:demo"]
    )  # created_at/usage_count 付き正常レコード
    # created_at/usage_count が null の legacy レコードを直接配置（save 経由では作れない）。
    (km.knowledge_dir / "legacy.json").write_text(
        json.dumps(
            {
                "id": "legacy",
                "title": "t",
                "content": "c",
                "created_at": None,
                "usage_count": None,
                "tags": ["repo:demo"],
            }
        ),
        encoding="utf-8",
    )

    # いずれの経路も旧コードはソートキー算出（None<str / int(None)）でクラッシュしていた。
    assert "legacy" in {e.get("id") for e in km.get_active_entries(limit=50)}  # created_at sort
    assert "legacy" in {
        e.get("id") for e in km.get_by_importance(limit=50)
    }  # usage_count+created_at
    assert "legacy" in {
        e.get("id") for e in km.get_for_repo("demo", limit=50)
    }  # usage_count+created_at


def test_arithmetic_paths_tolerate_null_usage_count_and_quality_score(tmp_path):
    """usage_count/quality_score が null の生 JSON 知識レコードで increment/昇格判定が落ちない。

    回帰（C70 が sort キーを硬化した後に残った非 sort の兄弟・C71）:
    - ``record_knowledge_access``: ``int(record.get("usage_count", 0)) + 1`` → null で ``int(None)``
      TypeError（知識アクセスのたびに発火する live write 経路）。
    - ``promote_to_best_practice`` / ``auto_promote_high_quality``:
      ``float(record.get("quality_score", 0))`` → null で ``float(None)`` TypeError（昇格処理を丸ごと落とす）。
    いずれも ``.get(k, 0)`` は **キーが null 値で存在すると default でなく None を返す** 罠
    （[[get-default-none-footgun]]）。
    """
    km = KnowledgeManager(tmp_path)
    # quality_score/usage_count が null の legacy レコードを直接配置（save 経由では作れない）。
    (km.knowledge_dir / "legacy.json").write_text(
        json.dumps(
            {
                "id": "legacy",
                "title": "t",
                "content": "c",
                "usage_count": None,
                "quality_score": None,
                "tags": ["repo:demo"],
            }
        ),
        encoding="utf-8",
    )

    # 旧コードは int(None)+1 でクラッシュ。新コードは null→0 として 0+1=1 に increment。
    km.record_knowledge_access(["repo:demo"])
    assert km._load_by_id("legacy").get("usage_count") == 1

    # 旧コードは float(None) でクラッシュ。新コードは null→0.0 として昇格しない（0.0 < 8 / < threshold）。
    assert km.promote_to_best_practice("legacy") is False  # 0.0 < 8 で昇格せず（クラッシュしない）

    # 非 null の有効スコアは同じ coerce 経路を通っても従来どおり昇格する（bit-for-bit 等価の固定）。
    (km.knowledge_dir / "good.json").write_text(
        json.dumps(
            {"id": "good", "title": "t", "content": "c", "quality_score": 9.0, "tags": ["repo:x"]}
        ),
        encoding="utf-8",
    )
    assert km.promote_to_best_practice("good") is True  # 9.0 >= 8 → 昇格
    # auto_promote: null レコード(0.0<8 で skip)も昇格済 good(best_practice で skip)もクラッシュさせない。
    assert km.auto_promote_high_quality() == 0


class TestKnowledgeManager:
    def test_save_and_get_insights(self, km):
        km.save_insight("import cleanup", "Python imports could be cleaner.", tags=["analysis"])
        insights = km.get_insights(tags=["analysis"])
        assert len(insights) == 1
        assert insights[0]["content"] == "Python imports could be cleaner."

    def test_filter_by_tag(self, km):
        km.save_insight("analysis insight", "content A", tags=["analysis"])
        km.save_insight("execution insight", "content B", tags=["execution"])
        assert len(km.get_insights(tags=["analysis"])) == 1
        assert len(km.get_insights(tags=["execution"])) == 1
        assert len(km.get_insights()) == 2

    def test_context_for_agent(self, km):
        km.save_insight("Use type hints", "Use type hints throughout.", tags=["analysis"])
        km.save_insight("Avoid bare excepts", "Avoid bare excepts.", tags=["analysis"])
        km.save_insight("Created branch", "Created branch fix/issue-1.", tags=["execution"])
        ctx = km.get_context_for_agent(tags=["analysis"], limit=5)
        assert "type hints" in ctx or "bare excepts" in ctx

    def test_max_insights_respected(self, km):
        for i in range(10):
            km.save_insight(f"insight {i}", f"content {i}", tags=["analysis"])
        insights = km.get_insights(tags=["analysis"], limit=3)
        assert len(insights) <= 3

    def test_empty_context_returns_string(self, km):
        ctx = km.get_context_for_agent(tags=["nonexistent"])
        assert isinstance(ctx, str)

    def test_persistence(self, tmp_path):
        km1 = KnowledgeManager(tmp_path)
        km1.save_insight("Persistent", "Persistent insight.", tags=["test"])
        km2 = KnowledgeManager(tmp_path)
        insights = km2.get_insights(tags=["test"])
        assert len(insights) == 1
        assert insights[0]["content"] == "Persistent insight."
