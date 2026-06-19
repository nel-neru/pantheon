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
