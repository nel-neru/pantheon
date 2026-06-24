"""core/vault/slug.py — 決定論・衝突安全・改名耐性。"""

from __future__ import annotations

from core.vault.slug import human_slug, note_filename, short_id


def test_human_slug_is_deterministic():
    assert human_slug("Atomic writes") == human_slug("Atomic writes")


def test_human_slug_collapses_separators_and_strips_forbidden():
    assert human_slug("  Atomic   writes / torn:state  ") == "Atomic-writes-tornstate"
    # Windows 禁止文字（<>:"/\|?*）は除去される。
    assert "/" not in human_slug("a/b:c*d?e")
    assert "\\" not in human_slug("a\\b")


def test_human_slug_preserves_japanese():
    # CJK は保持（Obsidian / 近代 FS で扱える）。空白はハイフンに畳む。
    assert human_slug("原子的 書き込み") == "原子的-書き込み"


def test_human_slug_empty_falls_back_to_note():
    assert human_slug("***") == "note"
    assert human_slug("") == "note"


def test_human_slug_truncates_to_max_len():
    out = human_slug("a" * 200, max_len=60)
    assert len(out) == 60


def test_short_id_uses_uuid_tail_and_is_stable():
    sid = short_id("insight:1234abcd-5678-90ef-aaaa-bbbbccccdddd")
    assert sid == short_id("insight:1234abcd-5678-90ef-aaaa-bbbbccccdddd")
    assert len(sid) == 8
    # 末尾英数字を使う（uuid 末尾）。
    assert sid == "ccccdddd"


def test_short_id_falls_back_to_hash_for_degenerate_ids():
    sid = short_id("::::")  # 英数字なし → ハッシュ由来
    assert len(sid) == 8
    assert sid == short_id("::::")


def test_note_filename_rename_stability():
    # title を変えても short_id（＝id 由来）は不変 → ファイルの追跡可能性が保たれる。
    entry_id = "pb:1111aaaa-2222-3333-4444-555566667777"
    f1 = note_filename("Old title", entry_id)
    f2 = note_filename("Completely different title", entry_id)
    assert f1.endswith("-66667777.md")
    assert f2.endswith("-66667777.md")
    assert f1 != f2  # slug 部分は変わる


def test_distinct_uuids_yield_distinct_filenames():
    a = note_filename("x", "insight:aaaaaaaa-0000-0000-0000-000000000001")
    b = note_filename("x", "insight:bbbbbbbb-0000-0000-0000-000000000002")
    assert a != b
