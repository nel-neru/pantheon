"""サムネ・キャラ設定画（asset_prompts ＋ story thumbnail/characters CLI）の検証。

プロンプト構築はカノンの style_suffix/negative を必ず注入（独自性）。CLI は generate_images を
注入差し替えして配線・registry 書き戻しを検証（実 API/鍵不要）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import yaml

from core.illustration_story.asset_prompts import character_prompts, thumbnail_prompt
from core.orchestration.company_plugins import install_company_plugin
from core.platform.state import PlatformStateManager


def _canon():
    return {
        "style_bible": {
            "style_suffix": "risograph flat illustration",
            "negative_prompt_bank": ["3d render", "watermark, text"],
        },
        "character_registry": {
            "characters": [
                {
                    "id": "keeper",
                    "name": "灯台守",
                    "base_seed": 101,
                    "face": "年配",
                    "outfit": "紺コート",
                },
                {"id": "cat", "name": "老猫", "base_seed": 103, "face": "灰色", "outfit": "赤い糸"},
            ]
        },
    }


def test_thumbnail_prompt_injects_canon_style():
    brief = {
        "logline": "灯台の光",
        "metadata": {
            "thumbnail_brief": {
                "composition": "灯台守のアップ",
                "focal_color": "#D7263D",
                "aspect": "16:9",
            }
        },
    }
    p = thumbnail_prompt(brief, _canon())
    assert p["shot_id"] == "thumbnail"
    assert "灯台守のアップ" in p["positive"] and "#D7263D" in p["positive"]
    assert "risograph" in p["style_suffix"]
    assert "watermark" in p["negative_prompt"]
    assert p["aspect"] == "16:9"


def test_character_prompts_one_per_character_with_style_and_seed():
    ps = character_prompts(_canon())
    assert [p["shot_id"] for p in ps] == ["keeper", "cat"]
    for p in ps:
        assert "model sheet" in p["positive"]
        assert "risograph" in p["style_suffix"]
        assert p["negative_prompt"]
    assert ps[0]["base_seed"] == 101  # 記録として seed を載せる


class _FakeResult:
    def __init__(self, shot_id, path):
        self.shot_id = shot_id
        self.ok = True
        self.path = path
        self.error = ""


def _fake_generate(
    prompts, *, out_dir, provider, model=None, platform_home=None, transport=None, write_bytes=None
):
    """generate_images の差し替え（鍵不要・ダミー png を書く）。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for p in prompts:
        path = out / f"{p['shot_id']}.png"
        path.write_bytes(b"\x89PNG\r\n")
        results.append(_FakeResult(p["shot_id"], str(path)))
    return results


def test_cli_thumbnail_generates_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    monkeypatch.setattr("core.media.image_gen.generate_images", _fake_generate)
    psm = PlatformStateManager(platform_home=tmp_path)
    org_name = install_company_plugin("illustration_story_youtube", psm=psm)["org_name"]

    from commands.story import cmd_story_brief, cmd_story_thumbnail

    asyncio.run(
        cmd_story_brief(
            SimpleNamespace(org=org_name, ep=1, format="long_form"), get_psm=lambda: psm
        )
    )
    asyncio.run(
        cmd_story_thumbnail(
            SimpleNamespace(org=org_name, ep=1, provider="gemini"), get_psm=lambda: psm
        )
    )

    org = psm.load_organization_by_name(org_name)
    thumb = Path(org.workspace_path) / "episodes" / "ep-01" / "thumbnail.png"
    assert thumb.exists()
    assert "サムネを生成" in capsys.readouterr().out


def test_cli_characters_generates_and_registers_canonical_sheets(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    monkeypatch.setattr("core.media.image_gen.generate_images", _fake_generate)
    psm = PlatformStateManager(platform_home=tmp_path)
    org_name = install_company_plugin("illustration_story_youtube", psm=psm)["org_name"]

    from commands.story import cmd_story_characters

    asyncio.run(
        cmd_story_characters(SimpleNamespace(org=org_name, provider="gemini"), get_psm=lambda: psm)
    )

    org = psm.load_organization_by_name(org_name)
    cdir = Path(org.workspace_path) / "canon" / "characters"
    # RED THREAD の4キャラ設定画が生成される
    assert (cdir / "lighthouse_keeper.png").exists()
    assert (cdir / "old_cat.png").exists()
    # canonical_sheet が registry に書き戻される（連続性アンカー）
    reg = yaml.safe_load(
        (Path(org.workspace_path) / "canon" / "character_registry.yaml").read_text(encoding="utf-8")
    )
    sheets = {c["id"]: c.get("canonical_sheet") for c in reg["characters"]}
    assert sheets["lighthouse_keeper"] and sheets["lighthouse_keeper"].endswith(
        "lighthouse_keeper.png"
    )
