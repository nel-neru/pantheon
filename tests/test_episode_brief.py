"""エピソードブリーフ生成（core/illustration_story）と `pantheon story brief` の検証。

決定論で、カノン由来の署名スタイルと固定 seed を全画像プロンプトへ注入し（独自性・連続性）、
画像生成/動画組立/アップロードは human_handoff として正直に外部へ渡すことを固定する。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import yaml

from core.illustration_story.episode_brief import (
    build_episode_brief,
    load_canon,
    next_unproduced_episode,
)
from core.orchestration.company_plugins import install_company_plugin
from core.platform.state import PlatformStateManager


def _canon():
    return {
        "style_bible": {
            "style_suffix": "limited-palette risograph paper-cut flat illustration, red thread motif",
            "palette": {"thread_red": "#D7263D"},
            "negative_prompt_bank": ["3d render", "watermark, text"],
            "aspect_ratios": {"long_form": "16:9", "shorts": "9:16"},
        },
        "character_registry": {
            "characters": [
                {
                    "id": "lighthouse_keeper",
                    "name": "灯台守",
                    "base_seed": 101001,
                    "face": "年配",
                    "outfit": "紺コート",
                },
            ]
        },
        "series_canon": {
            "premise": "静かな港町の twist 物語",
            "arc": {"acts": [{"name": "Thread Appears", "episodes": "1-10"}]},
            "backlog": [
                {
                    "ep": 1,
                    "logline": "灯台守の光は赤い糸の先の誰かへ向いていた",
                    "advances_arc": True,
                    "cast": ["lighthouse_keeper"],
                },
                {"ep": 2, "logline": "迷子が赤い糸をたぐる", "advances_arc": False, "cast": []},
            ],
        },
    }


def test_build_episode_brief_locks_style_and_seeds():
    brief = build_episode_brief(
        _canon(),
        episode_no=1,
        logline="灯台守の光は赤い糸の先へ",
        cast_ids=["lighthouse_keeper"],
        advances_arc=True,
    )
    assert brief["episode_no"] == 1
    assert brief["act"] == "Thread Appears"  # arc 範囲から解決
    assert brief["advances_arc"] is True
    # 全画像プロンプトに署名スタイル・negative・固定 seed・aspect が注入される（独自性・連続性）
    assert brief["image_prompts"]
    for p in brief["image_prompts"]:
        assert "risograph" in p["style_suffix"]
        assert p["negative_prompt"]
        assert p["aspect"] == "16:9"
        assert p["character_refs"] == [{"id": "lighthouse_keeper", "base_seed": 101001}]
    # 2 ビート / ショットに赤い糸の配置 / 連続性ロックの記録
    assert [b["beat"] for b in brief["beats"]] == ["setup", "twist"]
    assert all(s["thread_placement"] for s in brief["shot_list"])
    assert brief["originality_continuity_lock"]["character_seeds"] == {"lighthouse_keeper": 101001}
    # メタ・タイムライン・クロス投稿
    assert brief["metadata"]["title"].startswith("RED THREAD #1")
    assert brief["timeline_spec"]["shots"]
    assert set(brief["cross_post"]) == {"tiktok", "reels", "x"}


def test_human_handoff_routes_external_legs_honestly():
    """画像生成・動画組立・アップロードは Pantheon でやらず human_handoff に明記（見かけ自動にしない）。"""
    brief = build_episode_brief(
        _canon(), episode_no=1, logline="x", cast_ids=[], advances_arc=False
    )
    handoff = " / ".join(brief["human_handoff"])
    assert "画像生成" in handoff
    assert "動画組立" in handoff
    assert "アップロード" in handoff


def test_shorts_format_uses_vertical_aspect():
    brief = build_episode_brief(
        _canon(), episode_no=2, logline="迷子", cast_ids=[], advances_arc=False, fmt="shorts"
    )
    assert brief["format"] == "shorts"
    assert all(p["aspect"] == "9:16" for p in brief["image_prompts"])
    assert brief["metadata"]["title"].startswith("[Shorts]")


def test_next_unproduced_episode_advances(tmp_path):
    canon = _canon()
    edir = tmp_path / "episodes"
    # 何も無い → 最小話 ep1
    first = next_unproduced_episode(canon, edir)
    assert first["episode_no"] == 1 and first["cast_ids"] == ["lighthouse_keeper"]
    # ep1 を生成済みにする → 次は ep2
    edir.mkdir(parents=True)
    (edir / "ep-01.yaml").write_text("x", encoding="utf-8")
    assert next_unproduced_episode(canon, edir)["episode_no"] == 2


def test_load_canon_robust_to_missing(tmp_path):
    canon = load_canon(tmp_path / "no-such-ws")
    assert canon == {"style_bible": {}, "character_registry": {}, "series_canon": {}}


def test_cli_story_brief_end_to_end(tmp_path, monkeypatch, capsys):
    """会社プラグイン install → pantheon story brief で ep-01 ブリーフが生成され、再実行で ep-02 へ進む。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    psm = PlatformStateManager(platform_home=tmp_path)
    result = install_company_plugin("illustration_story_youtube", psm=psm)
    org_name = result["org_name"]

    from commands.story import cmd_story_brief

    asyncio.run(
        cmd_story_brief(
            SimpleNamespace(org=org_name, ep=None, format="long_form"), get_psm=lambda: psm
        )
    )
    out = capsys.readouterr().out
    assert "エピソードブリーフを生成" in out

    org = psm.load_organization_by_name(org_name)
    ep1 = Path(org.workspace_path) / "episodes" / "ep-01.yaml"
    assert ep1.exists()
    brief = yaml.safe_load(ep1.read_text(encoding="utf-8"))
    assert brief["episode_no"] == 1
    # 実カノン（RED THREAD）の署名スタイルが全プロンプトに乗る
    assert brief["image_prompts"] and all(
        "risograph" in p["style_suffix"] for p in brief["image_prompts"]
    )
    assert brief["human_handoff"]

    # 再実行で backlog を消化して ep-02 へ進む（自律運営の「次の一手」）
    asyncio.run(
        cmd_story_brief(
            SimpleNamespace(org=org_name, ep=None, format="long_form"), get_psm=lambda: psm
        )
    )
    assert (Path(org.workspace_path) / "episodes" / "ep-02.yaml").exists()
