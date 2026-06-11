"""C-2: デザインスタイルパックとローダーのテスト。"""

from __future__ import annotations

import pytest

from core.content import design_style_loader as dsl


@pytest.fixture(autouse=True)
def _clear_cache():
    dsl.load_style.cache_clear()
    yield
    dsl.load_style.cache_clear()


def test_bundled_styles_present():
    styles = dsl.list_styles()
    for expected in ("minimal", "luxury", "art", "3d", "pixel", "vibrant"):
        assert expected in styles


def test_each_style_has_prompt_and_palette():
    for sid in dsl.list_styles():
        addon = dsl.get_style_prompt_addon(sid)
        assert addon  # 全スタイルに生成指針がある
        palette = dsl.get_palette(sid)
        assert "primary" in palette and palette["primary"].startswith("#")


def test_luxury_prompt_addon_content():
    addon = dsl.get_style_prompt_addon("luxury")
    assert "高級感" in addon or "ラグジュアリー" in addon


def test_unknown_style_returns_empty():
    assert dsl.get_style_prompt_addon("nonexistent") == ""
    assert dsl.get_palette("nonexistent") == {}
    assert dsl.load_style("") is None


def test_style_summaries_shape():
    summaries = dsl.list_style_summaries()
    assert len(summaries) >= 6
    one = next(s for s in summaries if s["id"] == "pixel")
    assert one["name"] == "ピクセル"
    assert one["palette"]["accent"].startswith("#")
    assert one["font_family"]


def test_custom_dir_override(tmp_path, monkeypatch):
    (tmp_path / "custom.yaml").write_text(
        'id: custom\nname: カスタム\nprompt_addon: テスト指針\npalette:\n  primary: "#000000"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(dsl, "_styles_dir", lambda: tmp_path)
    dsl.load_style.cache_clear()
    assert "custom" in dsl.list_styles()
    assert dsl.get_style_prompt_addon("custom") == "テスト指針"
