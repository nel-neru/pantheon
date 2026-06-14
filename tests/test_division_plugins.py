"""2階層プラグインの事業部側（core.orchestration.division_plugins）のテスト。"""

from __future__ import annotations

import pytest

from core.orchestration.division_plugins import (
    add_division_plugin,
    get_division_plugin,
    load_company_plugins,
    load_division_plugins,
)
from core.org_factory import create_default_organization


def test_load_division_plugins_has_catalog():
    plugins = load_division_plugins()
    ids = {p["id"] for p in plugins}
    assert "x_audience" in ids
    assert "note_monetization" in ids
    # 各プラグインは department 定義を持つ
    for p in plugins:
        assert isinstance(p.get("department"), dict)
        assert p["department"].get("name")


def test_get_division_plugin_known_and_unknown():
    assert get_division_plugin("x_audience") is not None
    assert get_division_plugin("does_not_exist") is None


def test_add_division_plugin_appends_division_with_agents():
    org = create_default_organization("Test Co", "テスト用")
    before = len(org.divisions)
    division = add_division_plugin(org, "x_audience")

    assert len(org.divisions) == before + 1
    assert division.name == "X集客事業部"
    assert len(division.teams) >= 1
    # SpecialistAgent の skills は 2〜3（_build_team の正規化）
    for team in division.teams:
        for agent in team.agents:
            assert 2 <= len(agent.skills) <= 3


def test_add_division_plugin_unknown_raises():
    org = create_default_organization("Test Co", "テスト用")
    with pytest.raises(ValueError):
        add_division_plugin(org, "no_such_plugin")


def test_load_company_plugins_lists_department_templates():
    plugins = load_company_plugins()
    ids = {p["id"] for p in plugins}
    # 同梱テンプレートが会社プラグインとして列挙される
    assert "sns_growth" in ids
    for p in plugins:
        assert "division_count" in p


# ------------------------------------------------------------------
# PT-2: テンプレ形エントリの自動展開 + scaffold CLI
# ------------------------------------------------------------------


def test_template_form_entries_are_expanded():
    """department を書かない §7.4 テンプレ形エントリがプリセットから展開される。"""
    plugins = load_division_plugins()
    by_id = {p["id"]: p for p in plugins}
    # 新カタログの代表（compact 形で定義したもの）
    assert "youtube_audience" in by_id
    assert "membership_subscription" in by_id
    yt = by_id["youtube_audience"]
    dept = yt["department"]
    assert dept["type"] == "audience_development"  # audience プリセット
    assert len(dept["teams"]) == 2
    for team in dept["teams"]:
        assert 2 <= len(team["required_skills"]) <= 3


def test_add_division_from_template_entry():
    """テンプレ形エントリでも add_division_plugin で Division を組み立てられる。"""
    org = create_default_organization("Tpl Co", "テスト用")
    division = add_division_plugin(org, "youtube_audience")
    assert division.name == "YouTube集客事業部"
    assert len(division.teams) >= 1
    for team in division.teams:
        for agent in team.agents:
            assert 2 <= len(agent.skills) <= 3


def test_pt3_catalog_breadth_note_and_funnel_variants():
    """PT-3: §7.4 #2 note有料記事作成 + #4 フルファネル残3バリアントがカタログに揃う。"""
    by_id = {p["id"]: p for p in load_division_plugins()}
    # §7.4 #2: 作成特化（販売側 note_monetization とは別 id）
    assert "note_paid_article" in by_id
    assert by_id["note_paid_article"]["category"] == "content"
    assert "note_monetization" in by_id  # 販売側は引き続き別に存在

    # §7.4 #4: 差別化された 3 つのフルファネル（汎用 full_funnel に加えて）
    variants = [
        "funnel_short_video_digital",
        "funnel_content_multiplatform",
        "funnel_ai_note_affiliate",
    ]
    for vid in variants:
        assert vid in by_id, vid
        assert by_id[vid]["category"] == "full_funnel"

    # 差別化の検証: 各バリアントのチーム名集合が互いに異なる（汎用プリセットの使い回しでない）。
    team_sets = {
        vid: frozenset(t["name"] for t in by_id[vid]["department"]["teams"]) for vid in variants
    }
    assert len({*team_sets.values()}) == len(variants)  # 全て異なる構成


def test_pt3_funnel_variants_build_with_valid_agents():
    """PT-3: フルファネルバリアントが add_division_plugin で組み立て可能（skills 2〜3）。"""
    org = create_default_organization("Funnel Co", "テスト")
    division = add_division_plugin(org, "funnel_short_video_digital")
    assert len(division.teams) == 3
    for team in division.teams:
        for agent in team.agents:
            assert 2 <= len(agent.skills) <= 3


def test_scaffold_division_cli_write_then_load(tmp_path, monkeypatch):
    """scaffold-division --write で追記したテンプレ形が loader に展開されて見える。"""
    import argparse
    import asyncio

    import core.orchestration.division_plugins as dp
    import core.paths as paths_mod
    from commands.plugin import cmd_plugin_scaffold_division

    catalog = tmp_path / "division_plugins.yaml"
    catalog.write_text(
        "plugins:\n  - id: seed\n    label: Seed\n    category: operations\n",
        encoding="utf-8",
    )

    def fake_resource_path(*parts):
        if parts and parts[-1] == "division_plugins.yaml":
            return catalog
        return paths_mod.resource_path(*parts)

    # コマンド側（書込）と loader 側（読込）の両方の resource_path を tmp に向ける。
    monkeypatch.setattr("core.paths.resource_path", fake_resource_path)
    monkeypatch.setattr(dp, "resource_path", fake_resource_path)

    args = argparse.Namespace(
        id="my_newsletter",
        label="マイメルマガ事業部",
        category="audience",
        description="メルマガ集客",
        mission="",
        write=True,
    )
    asyncio.run(cmd_plugin_scaffold_division(args, get_psm=lambda: None))

    plugin = dp.get_division_plugin("my_newsletter")
    assert plugin is not None
    assert plugin["department"]["type"] == "audience_development"

    # 冪等: 同 id で再 --write しても重複追記しない。
    asyncio.run(cmd_plugin_scaffold_division(args, get_psm=lambda: None))
    ids = [p["id"] for p in dp.load_division_plugins()]
    assert ids.count("my_newsletter") == 1
