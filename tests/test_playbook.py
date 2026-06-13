"""PlaybookStore のテスト（P2.3）。tmp_path を直接注入し get_platform_home に依存しない。"""

from __future__ import annotations

from core.intelligence.playbook import PlaybookEntry, PlaybookStore


def test_add_and_list(tmp_path):
    store = PlaybookStore(platform_home=tmp_path)
    entry = store.add("Use bullet points", "Short bullets convert better", category="copy")

    assert isinstance(entry, PlaybookEntry)
    assert entry.entry_id.startswith("pb:")
    assert entry.usefulness_score == 0.0
    assert entry.usage_count == 0
    assert entry.created_at and entry.created_at == entry.updated_at

    listed = store.list_entries()
    assert len(listed) == 1
    assert listed[0].entry_id == entry.entry_id
    assert listed[0].title == "Use bullet points"


def test_list_filters_by_category(tmp_path):
    store = PlaybookStore(platform_home=tmp_path)
    store.add("A", "a", category="copy")
    store.add("B", "b", category="seo")
    store.add("C", "c", category="copy")

    copy_entries = store.list_entries(category="copy")
    assert {e.title for e in copy_entries} == {"A", "C"}
    assert store.list_entries(category="seo")[0].title == "B"
    assert store.list_entries(category="missing") == []


def test_record_use_scoring_and_count(tmp_path):
    store = PlaybookStore(platform_home=tmp_path)
    entry = store.add("tactic", "body")

    after_success = store.record_use(entry.entry_id, success=True)
    assert after_success is not None
    assert after_success.usage_count == 1
    assert after_success.usefulness_score == 1.0

    after_failure = store.record_use(entry.entry_id, success=False)
    assert after_failure is not None
    assert after_failure.usage_count == 2
    assert after_failure.usefulness_score == 0.5
    assert after_failure.updated_at >= after_failure.created_at

    # 永続化されていること（再ロードしても値が一致）
    reloaded = store.list_entries()[0]
    assert reloaded.usage_count == 2
    assert reloaded.usefulness_score == 0.5


def test_record_use_unknown_id_returns_none(tmp_path):
    store = PlaybookStore(platform_home=tmp_path)
    store.add("x", "y")
    assert store.record_use("pb:does-not-exist", success=True) is None


def test_top_orders_by_usefulness_desc(tmp_path):
    store = PlaybookStore(platform_home=tmp_path)
    low = store.add("low", "l")
    high = store.add("high", "h")
    mid = store.add("mid", "m")

    store.record_use(high.entry_id, success=True)
    store.record_use(high.entry_id, success=True)  # score 2.0
    store.record_use(mid.entry_id, success=True)  # score 1.0
    store.record_use(low.entry_id, success=False)  # score -0.5

    ranked = store.top()
    assert [e.title for e in ranked] == ["high", "mid", "low"]

    limited = store.top(limit=2)
    assert [e.title for e in limited] == ["high", "mid"]


def test_tmp_path_injection_does_not_touch_global_home(tmp_path):
    store = PlaybookStore(platform_home=tmp_path)
    store.add("only here", "content")
    assert (tmp_path / "playbooks.json").exists()

    # 別の tmp_path ストアは独立（共有グローバル状態を使っていない）
    other = PlaybookStore(platform_home=tmp_path / "other")
    assert other.list_entries() == []
