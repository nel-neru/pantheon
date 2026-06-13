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
