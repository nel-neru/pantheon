"""core/vault/format.py — parse/render の決定論・寛容 parse・wikilink・ハッシュ。"""

from __future__ import annotations

from core.vault.format import (
    body_hash,
    emit_wikilink,
    meta_hash,
    parse_note,
    parse_wikilinks,
    render_note,
)


def test_render_parse_round_trip_preserves_frontmatter():
    fm = {
        "pantheon_id": "abc-123",
        "pantheon_type": "insight",
        "title": "原子的書き込み",
        "tags": ["best_practice", "repo:Foo"],
        "usage_count": 12,
        "quality_score": 8.5,
        "archived": False,
    }
    body = "# 原子的書き込み\n\n本文テキスト。"
    note = parse_note(render_note(fm, body))
    assert note.frontmatter == fm
    assert note.body.strip() == body.strip()


def test_render_is_byte_deterministic_regardless_of_key_order():
    a = {"pantheon_id": "x", "title": "t", "pantheon_type": "insight"}
    b = {"title": "t", "pantheon_type": "insight", "pantheon_id": "x"}
    assert render_note(a, "body") == render_note(b, "body")
    # 同一入力は必ず同一バイト列（冪等 export の前提）。
    assert render_note(a, "body") == render_note(a, "body")


def test_render_orders_control_keys_first():
    text = render_note({"title": "t", "pantheon_id": "x", "pantheon_type": "insight"}, "b")
    # 制御キー pantheon_id が title より前に来る。
    assert text.index("pantheon_id") < text.index("title")


def test_parse_tolerant_no_frontmatter():
    note = parse_note("ただの本文\n2 行目")
    assert note.frontmatter == {}
    assert note.body == "ただの本文\n2 行目"


def test_parse_tolerant_non_dict_yaml():
    note = parse_note("---\n- a\n- b\n---\nbody")
    assert note.frontmatter == {}
    assert note.body.strip() == "body"


def test_parse_tolerant_broken_yaml():
    note = parse_note("---\nfoo: [unclosed\n---\nbody")
    assert note.frontmatter == {}
    assert note.body.strip() == "body"


def test_parse_wikilinks_types_and_alias():
    links = parse_wikilinks("see [[org:Foo]] and [[insight:abc|Bar]] and [[plain]]")
    assert [(link.type, link.target, link.alias) for link in links] == [
        ("org", "Foo", ""),
        ("insight", "abc", "Bar"),
        ("", "plain", ""),
    ]
    assert links[0].node_id == "org:Foo"
    assert links[2].node_id == "plain"


def test_emit_wikilink():
    assert emit_wikilink("org", "Foo") == "[[org:Foo]]"
    assert emit_wikilink("insight", "abc", "Bar") == "[[insight:abc|Bar]]"
    assert emit_wikilink("", "plain") == "[[plain]]"


def test_body_hash_ignores_trailing_whitespace_and_newlines():
    assert body_hash("a\nb  ") == body_hash("a\nb")
    assert body_hash("a\r\nb") == body_hash("a\nb")
    assert body_hash("a") != body_hash("b")


def test_meta_hash_ignores_volatile_control_keys():
    base = {"pantheon_id": "x", "title": "t"}
    with_volatile = {
        **base,
        "pantheon_synced_at": "2026-06-25T00:00:00Z",
        "pantheon_body_hash": "sha256:deadbeef",
        "pantheon_meta_hash": "sha256:cafe",
    }
    assert meta_hash(base) == meta_hash(with_volatile)
    assert meta_hash(base) != meta_hash({"pantheon_id": "x", "title": "CHANGED"})
