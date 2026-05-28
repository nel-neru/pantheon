"""Unit tests for KnowledgeManager"""
import tempfile
from pathlib import Path

import pytest

from core.knowledge.manager import KnowledgeManager


@pytest.fixture
def km(tmp_path):
    return KnowledgeManager(tmp_path)


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
