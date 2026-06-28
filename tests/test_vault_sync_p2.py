"""core/vault/sync.py Phase 2 — 双方向 import・3-way 競合・edit_note・収益インテグリティ。"""

from __future__ import annotations

from pathlib import Path

from core.intelligence.playbook import PlaybookStore
from core.knowledge.manager import KnowledgeManager
from core.metrics.outcomes import OutcomeStore
from core.vault import build_default_sync, get_vault_dir
from core.vault.format import parse_note, render_note


def _edit_note_content(path: Path, new_content: str) -> None:
    """ユーザーが Obsidian で本文を書き換えた状況を再現する（frontmatter は据え置き）。"""
    note = parse_note(path.read_text(encoding="utf-8"))
    path.write_text(render_note(note.frontmatter, new_content), encoding="utf-8")


def _insight_note(vault: Path) -> Path:
    return next((vault / "insights").glob("*.md"))


def test_import_writes_user_edit_back_to_store(tmp_path):
    km = KnowledgeManager(tmp_path)
    km.save_insight("Title", "original content", tags=["x"], source_org="Foo")
    sync = build_default_sync(tmp_path)
    vault = get_vault_dir(tmp_path)
    sync.export()

    _edit_note_content(_insight_note(vault), "ユーザーが書き換えた本文")
    result = sync.sync()

    assert result["import"]["imported"] == 1
    assert km.get_insights(limit=10)[0]["content"] == "ユーザーが書き換えた本文"


def test_import_noop_when_no_user_edit(tmp_path):
    KnowledgeManager(tmp_path).save_insight("T", "c", tags=["x"], source_org="Foo")
    sync = build_default_sync(tmp_path)
    sync.export()

    result = sync.import_vault()
    assert result.imported == 0
    assert result.conflicts == 0


def test_store_change_without_user_edit_refreshes_note(tmp_path):
    km = KnowledgeManager(tmp_path)
    eid = km.save_insight("T", "original", tags=["x"], source_org="Foo")
    sync = build_default_sync(tmp_path)
    vault = get_vault_dir(tmp_path)
    sync.export()

    km.update_insight(eid, content="store changed content")
    result = sync.sync()

    assert result["import"]["imported"] == 0
    note = parse_note(_insight_note(vault).read_text(encoding="utf-8"))
    assert "store changed content" in note.body


def test_divergent_edits_produce_conflict_and_preserve_store(tmp_path):
    km = KnowledgeManager(tmp_path)
    eid = km.save_insight("T", "original", tags=["x"], source_org="Foo")
    sync = build_default_sync(tmp_path)
    vault = get_vault_dir(tmp_path)
    sync.export()

    # ユーザーとストアが別内容に分岐
    _edit_note_content(_insight_note(vault), "ユーザーの版")
    km.update_insight(eid, content="ストアの版")
    result = sync.sync()

    assert result["import"]["conflicts"] == 1
    assert result["import"]["imported"] == 0
    # .conflict.md が両版を保全し、ストアは上書きされない
    conflicts = list((vault / "insights").glob("*.conflict.md"))
    assert len(conflicts) == 1
    assert km.get_insights(limit=10)[0]["content"] == "ストアの版"
    conflict_body = parse_note(conflicts[0].read_text(encoding="utf-8")).body
    assert "ユーザーの版" in conflict_body
    assert "ストアの版" in conflict_body


def test_conflict_held_blocks_further_import_and_export(tmp_path):
    km = KnowledgeManager(tmp_path)
    eid = km.save_insight("T", "original", tags=["x"], source_org="Foo")
    sync = build_default_sync(tmp_path)
    vault = get_vault_dir(tmp_path)
    sync.export()
    _edit_note_content(_insight_note(vault), "ユーザーの版")
    km.update_insight(eid, content="ストアの版")
    sync.sync()  # 競合発生

    # 競合中の再 sync は当該ノートを import も上書きもしない
    note_before = _insight_note(vault).read_text(encoding="utf-8")
    result = sync.sync()
    assert result["import"]["imported"] == 0
    assert _insight_note(vault).read_text(encoding="utf-8") == note_before
    assert "ユーザーの版" in note_before


def test_json_mirror_edit_rejected_and_truth_restored(tmp_path):
    oc = OutcomeStore(tmp_path)
    oc.record("Foo", "revenue", 100, source="note")
    sync = build_default_sync(tmp_path)
    vault = get_vault_dir(tmp_path)
    sync.export()

    note_path = next((vault / "outcomes").glob("*.md"))
    _edit_note_content(note_path, "確定収益を 999999 に書き換えた")
    result = sync.sync()

    assert result["import"]["rejected"] >= 1
    # 真値（読み取り専用ミラー）が復元され、ユーザー編集は .conflict.md に保全される
    restored = parse_note(note_path.read_text(encoding="utf-8")).body
    assert "読み取り専用ミラー" in restored
    assert list((vault / "outcomes").glob("*.conflict.md"))
    # 収益インテグリティ: OutcomeStore は不変
    assert OutcomeStore(tmp_path).summary_for_org("Foo").total_revenue == 100.0


def test_edit_note_gui_roundtrip_vault(tmp_path):
    km = KnowledgeManager(tmp_path)
    km.save_insight("T", "original", tags=["x"], source_org="Foo")
    sync = build_default_sync(tmp_path)
    vault = get_vault_dir(tmp_path)
    sync.export()

    rel = _insight_note(vault).relative_to(vault).as_posix()
    res = sync.edit_note(rel, "GUI で編集した本文")

    assert res["status"] == "accepted"
    assert km.get_insights(limit=10)[0]["content"] == "GUI で編集した本文"


def test_edit_note_gui_rejected_for_json_mirror(tmp_path):
    OutcomeStore(tmp_path).record("Foo", "revenue", 100, source="note")
    sync = build_default_sync(tmp_path)
    vault = get_vault_dir(tmp_path)
    sync.export()

    rel = next((vault / "outcomes").glob("*.md")).relative_to(vault).as_posix()
    res = sync.edit_note(rel, "改ざん")
    assert res["status"] == "rejected"
    assert OutcomeStore(tmp_path).summary_for_org("Foo").total_revenue == 100.0


def test_playbook_roundtrip(tmp_path):
    pb = PlaybookStore(tmp_path)
    pb.add("P", "original play", category="general", org_name="Foo")
    sync = build_default_sync(tmp_path)
    vault = get_vault_dir(tmp_path)
    sync.export()

    note_path = next((vault / "playbooks").glob("*.md"))
    _edit_note_content(note_path, "改善した施策")
    sync.sync()

    assert PlaybookStore(tmp_path).list_entries()[0].content == "改善した施策"


def test_status_and_doctor_report_conflicts(tmp_path):
    km = KnowledgeManager(tmp_path)
    eid = km.save_insight("T", "original", tags=["x"], source_org="Foo")
    sync = build_default_sync(tmp_path)
    vault = get_vault_dir(tmp_path)
    sync.export()
    _edit_note_content(_insight_note(vault), "ユーザーの版")
    km.update_insight(eid, content="ストアの版")
    sync.sync()

    assert sync.status()["conflict_count"] == 1
    assert sync.doctor()["conflicts"] == 1
    # 競合ノートは doctor のエラーにならない
    assert sync.doctor()["ok"] is True
