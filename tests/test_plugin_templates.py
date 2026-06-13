"""``core.orchestration.plugin_templates`` の雛形生成（PT-1 / 計画§6）テスト。

純粋関数なので tmp_path 不要。検証観点:
- division / company の各 scaffold が正しい形状・型値（DivisionType / AgentSkill）を返す
- full_funnel が 3 部門以上（audience+monetization 合成）になる
- 未知カテゴリは operations へフォールバックする
- 生成は決定論（同入力 → 等価出力）
- 生成した department は org_factory._build_division がそのまま食べられる
"""

from __future__ import annotations

from core.models.organization import AgentSkill, DivisionType
from core.orchestration.plugin_templates import (
    CATEGORY_PRESETS,
    scaffold_company_plugin,
    scaffold_division_plugin,
)
from core.org_factory import _build_division

# 有効な enum 値の集合（型値の検証に使う）。
_VALID_DIVISION_TYPES = {t.value for t in DivisionType}
_VALID_SKILLS = {s.value for s in AgentSkill}


# --- 事業部プラグイン --------------------------------------------------------


def test_scaffold_division_plugin_shape_and_types() -> None:
    """division 雛形が division_plugins.yaml と同形・有効な型値を返す。"""
    plugin = scaffold_division_plugin(
        "x_audience",
        "X集客事業部",
        "audience",
        description="X で集客する入口事業部",
        mission="X で獲得し収益化へ送客する",
    )

    # トップレベルのキーが厳密一致。
    assert set(plugin.keys()) == {"id", "label", "category", "description", "department"}
    assert plugin["id"] == "x_audience"
    assert plugin["label"] == "X集客事業部"
    assert plugin["category"] == "audience"
    assert plugin["description"] == "X で集客する入口事業部"

    dept = plugin["department"]
    assert set(dept.keys()) == {"name", "type", "mission", "teams"}
    assert dept["name"] == "X集客事業部"
    assert dept["mission"] == "X で獲得し収益化へ送客する"

    # type は DivisionType の有効な値。
    assert dept["type"] in _VALID_DIVISION_TYPES
    assert dept["type"] == "audience_development"

    # 各チームは name/mission/required_skills を持ち、skills は AgentSkill の値で 2〜3 個。
    assert dept["teams"], "teams は空であってはならない"
    for team in dept["teams"]:
        assert set(team.keys()) == {"name", "mission", "required_skills"}
        skills = team["required_skills"]
        assert 2 <= len(skills) <= 3
        assert all(s in _VALID_SKILLS for s in skills)


def test_scaffold_division_plugin_defaults_when_optional_omitted() -> None:
    """description / mission 省略時に決定的な既定文が入る。"""
    plugin = scaffold_division_plugin("note_sales", "note販売事業部", "monetization")
    dept = plugin["department"]

    assert dept["type"] == "monetization"
    assert dept["mission"]  # 空でない既定 mission
    assert plugin["description"]  # 空でない既定 description
    # label がそのまま department.name になる。
    assert dept["name"] == "note販売事業部"


def test_scaffold_division_plugin_full_funnel_has_three_or_more_teams() -> None:
    """full_funnel は audience + monetization を合成して 3 チーム以上になる。"""
    plugin = scaffold_division_plugin("growth_company", "集客→収益化事業部", "full_funnel")
    teams = plugin["department"]["teams"]

    # audience(2) + monetization(2) = 4 チーム。
    assert len(teams) >= 3
    assert len(teams) == 4

    team_names = [t["name"] for t in teams]
    # 双方のカテゴリのチームが含まれていること（合成の証拠）。
    assert "Growth Team" in team_names  # audience 由来
    assert "Sales Writing Team" in team_names  # monetization 由来

    # 合成後も全チームが有効な 2〜3 スキル。
    for team in teams:
        assert 2 <= len(team["required_skills"]) <= 3
        assert all(s in _VALID_SKILLS for s in team["required_skills"])


def test_scaffold_division_plugin_unknown_category_falls_back_to_operations() -> None:
    """未知カテゴリは operations 扱いになる。"""
    plugin = scaffold_division_plugin("mystery", "謎事業部", "does-not-exist")

    assert plugin["category"] == "operations"
    # operations プリセットの DivisionType。
    assert plugin["department"]["type"] == CATEGORY_PRESETS["operations"]["division_type"]
    assert plugin["department"]["type"] in _VALID_DIVISION_TYPES


def test_scaffold_division_plugin_all_presets_use_valid_enum_values() -> None:
    """全プリセットの type / required_skills が有効な enum 値であること（壊れたプリセット検出）。"""
    for category in CATEGORY_PRESETS:
        plugin = scaffold_division_plugin(f"id_{category}", f"label_{category}", category)
        dept = plugin["department"]
        assert dept["type"] in _VALID_DIVISION_TYPES
        for team in dept["teams"]:
            assert 2 <= len(team["required_skills"]) <= 3
            assert all(s in _VALID_SKILLS for s in team["required_skills"])


def test_scaffold_division_plugin_is_deterministic() -> None:
    """同じ入力からは等価な dict を返す（決定論・冪等）。"""
    a = scaffold_division_plugin("x", "ラベル", "content", description="d", mission="m")
    b = scaffold_division_plugin("x", "ラベル", "content", description="d", mission="m")
    assert a == b


def test_scaffold_division_plugin_department_builds_via_factory() -> None:
    """生成した department を _build_division がそのまま組み立てられる（統合）。"""
    plugin = scaffold_division_plugin("full", "フルファネル事業部", "full_funnel")
    division = _build_division(plugin["department"])

    assert division.name == "フルファネル事業部"
    assert isinstance(division.type, DivisionType)
    # 4 チーム → 各チーム 1 Specialist。
    assert len(division.teams) == 4
    for team in division.teams:
        assert team.agents
        for agent in team.agents:
            # SpecialistAgent.skills は min 2 / max 3 を満たす。
            assert 2 <= len(agent.skills) <= 3


# --- 会社プラグイン manifest -------------------------------------------------


def test_scaffold_company_plugin_shape() -> None:
    """company manifest が company_plugins.yaml と同形を返す。"""
    manifest = scaffold_company_plugin(
        "note_sales",
        "note 販売会社",
        "digital_content",
        divisions=["コンテンツ企画部", "記事制作部", "販売・マーケティング部"],
        initial_kpis=["月間有料記事公開数", "有料記事の売上（円）"],
        human_tasks=["有料記事の公開承認と価格設定"],
        weekly_review="週次で売上を確認する",
    )

    assert set(manifest.keys()) == {
        "id",
        "label",
        "genre",
        "description",
        "initial_kpis",
        "weekly_review",
        "human_tasks",
        "divisions",
    }
    assert manifest["id"] == "note_sales"
    assert manifest["label"] == "note 販売会社"
    assert manifest["genre"] == "digital_content"
    assert manifest["divisions"] == ["コンテンツ企画部", "記事制作部", "販売・マーケティング部"]
    assert manifest["initial_kpis"] == ["月間有料記事公開数", "有料記事の売上（円）"]
    assert manifest["human_tasks"] == ["有料記事の公開承認と価格設定"]
    assert manifest["weekly_review"] == "週次で売上を確認する"


def test_scaffold_company_plugin_divisions_from_category_preset() -> None:
    """divisions 未指定なら category プリセットの既定事業部名を与える。"""
    manifest = scaffold_company_plugin(
        "affiliate",
        "アフィリエイト会社",
        "affiliate_marketing",
        category="monetization",
    )

    assert manifest["divisions"] == list(CATEGORY_PRESETS["monetization"]["default_divisions"])
    assert manifest["divisions"], "プリセットから事業部名が来ること"


def test_scaffold_company_plugin_unknown_category_falls_back_to_operations() -> None:
    """divisions 未指定 + 未知 category は operations の既定事業部名にフォールバック。"""
    manifest = scaffold_company_plugin("x", "謎会社", "misc", category="nope")
    assert manifest["divisions"] == list(CATEGORY_PRESETS["operations"]["default_divisions"])


def test_scaffold_company_plugin_defaults_for_optional_lists() -> None:
    """initial_kpis / human_tasks 省略時は空リスト、weekly_review 省略時は空文字。"""
    manifest = scaffold_company_plugin("x", "会社", "genre")
    assert manifest["initial_kpis"] == []
    assert manifest["human_tasks"] == []
    assert manifest["weekly_review"] == ""
    # divisions は category(None→operations) プリセットから来る。
    assert manifest["divisions"] == list(CATEGORY_PRESETS["operations"]["default_divisions"])


def test_scaffold_company_plugin_is_deterministic() -> None:
    """同じ入力からは等価な manifest を返す（決定論・冪等）。"""
    kwargs = dict(
        divisions=["A部", "B部"],
        initial_kpis=["KPI1"],
        human_tasks=["承認タスク"],
        weekly_review="週次レビュー",
    )
    a = scaffold_company_plugin("id", "ラベル", "genre", **kwargs)
    b = scaffold_company_plugin("id", "ラベル", "genre", **kwargs)
    assert a == b


def test_scaffold_company_plugin_strips_blank_divisions() -> None:
    """divisions の空白要素は除去される。"""
    manifest = scaffold_company_plugin(
        "id", "ラベル", "genre", divisions=["有効部", "  ", "", "別の部"]
    )
    assert manifest["divisions"] == ["有効部", "別の部"]
