"""core/vault/sync.py — export 冪等・収益インテグリティ・ユーザー編集保全・status/doctor。"""

from __future__ import annotations

from pathlib import Path

from core.intelligence.playbook import PlaybookStore
from core.knowledge.manager import KnowledgeManager
from core.metrics.outcomes import OutcomeStore
from core.vault import OutcomeAdapter, build_default_sync, get_vault_dir
from core.vault.format import parse_note


def _seed(tmp_path: Path) -> None:
    km = KnowledgeManager(tmp_path)
    km.save_insight(
        "Atomic writes prevent torn state",
        "os.replace で原子的に差し替える。",
        tags=["best_practice"],
        source_org="Foo",
    )
    pb = PlaybookStore(tmp_path)
    pb.add(
        "Use dedupe_on_source",
        "1 回しか起きない事象は source で冪等化する。",
        category="revenue",
        org_name="Foo",
    )
    oc = OutcomeStore(tmp_path)
    oc.record("Foo", "revenue", 1000, source="note")
    oc.record("Foo", "impressions", 500, source="x")


def test_export_creates_notes_per_type(tmp_path):
    _seed(tmp_path)
    sync = build_default_sync(tmp_path)
    vault = get_vault_dir(tmp_path)

    stats = sync.export()

    assert stats.written == 3
    assert len(list((vault / "insights").glob("*.md"))) == 1
    assert len(list((vault / "playbooks").glob("*.md"))) == 1
    assert len(list((vault / "outcomes").glob("*.md"))) == 1
    assert (vault / "_pantheon.md").exists()


def test_export_is_idempotent(tmp_path):
    _seed(tmp_path)
    sync = build_default_sync(tmp_path)

    sync.export()
    second = sync.export()

    assert second.written == 0
    assert second.skipped == 3


def test_exported_note_has_control_block(tmp_path):
    _seed(tmp_path)
    sync = build_default_sync(tmp_path)
    vault = get_vault_dir(tmp_path)
    sync.export()

    note_path = next((vault / "insights").glob("*.md"))
    note = parse_note(note_path.read_text(encoding="utf-8"))
    assert note.frontmatter["pantheon_type"] == "insight"
    assert note.frontmatter["pantheon_canonical"] == "vault"
    assert note.frontmatter["pantheon_id"]
    assert note.frontmatter["title"] == "Atomic writes prevent torn state"
    assert note.frontmatter["pantheon_body_hash"].startswith("sha256:")
    # source_org への wikilink が本文に出る。
    assert "[[org:Foo]]" in note.body


def test_outcome_note_is_readonly_mirror(tmp_path):
    _seed(tmp_path)
    sync = build_default_sync(tmp_path)
    vault = get_vault_dir(tmp_path)
    sync.export()

    note_path = next((vault / "outcomes").glob("*.md"))
    note = parse_note(note_path.read_text(encoding="utf-8"))
    assert note.frontmatter["pantheon_canonical"] == "json"
    assert note.frontmatter["total_revenue"] == 1000.0
    assert "読み取り専用ミラー" in note.body
    # 確定収益（記録済みイベント）の合計のみを表示し、偽造しない。
    assert "確定収益" in note.body


def test_outcome_import_is_hard_rejected(tmp_path):
    # 収益インテグリティ: Vault 側の編集は決して記録収益へ反映しない。
    adapter = OutcomeAdapter(tmp_path)
    result = adapter.apply_import("outcome:Foo", {"total_revenue": 999999}, "fake")
    assert result.status == "rejected"


def test_export_never_mutates_outcomes_store(tmp_path):
    # 収益インテグリティ: export は OutcomeStore を読むだけで一切書き換えない。
    _seed(tmp_path)
    outcomes_json = OutcomeStore(tmp_path).outcomes_path
    before = outcomes_json.read_bytes()

    build_default_sync(tmp_path).export()

    assert outcomes_json.read_bytes() == before


def test_store_change_triggers_single_rewrite(tmp_path):
    _seed(tmp_path)
    sync = build_default_sync(tmp_path)
    sync.export()

    # insight の usage_count を変える（meta が変わる）→ そのノートだけ書き直される。
    KnowledgeManager(tmp_path).record_knowledge_access(["best_practice"])
    stats = sync.export()

    assert stats.written == 1
    assert stats.by_type.get("insight") == 1


def test_export_preserves_user_edits_when_store_unchanged(tmp_path):
    # Phase 1 の安全性: ストア内容が変わらなければ export はユーザー編集を上書きしない。
    _seed(tmp_path)
    sync = build_default_sync(tmp_path)
    vault = get_vault_dir(tmp_path)
    sync.export()

    note_path = next((vault / "playbooks").glob("*.md"))
    edited = note_path.read_text(encoding="utf-8") + "\n\nUSER EDIT ここはユーザーが追記した。"
    note_path.write_text(edited, encoding="utf-8")

    stats = sync.export()

    assert stats.written == 0
    assert "USER EDIT" in note_path.read_text(encoding="utf-8")


def test_status_reports_pending_then_clean(tmp_path):
    _seed(tmp_path)
    sync = build_default_sync(tmp_path)

    before = sync.status()
    assert before["total_entries"] == 3
    assert before["total_pending"] == 3

    sync.export()
    after = sync.status()
    assert after["total_pending"] == 0


def test_doctor_is_clean_after_export(tmp_path):
    _seed(tmp_path)
    sync = build_default_sync(tmp_path)
    sync.export()

    report = sync.doctor()
    assert report["ok"] is True
    assert report["issues"] == []
    assert report["checked"] == 3
    # _pantheon.md は管理対象外（unmanaged）としてカウントされ、エラーにならない。
    assert report["unmanaged"] >= 1
