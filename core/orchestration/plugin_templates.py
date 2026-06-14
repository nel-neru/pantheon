"""プラグイン雛形のテンプレ框組み（PT-1 / 計画§6）。

2階層プラグインマーケットプレイス（事業部プラグイン / 会社プラグイン manifest）の
**雛形を「テンプレから生成」する純粋関数群**を提供する。LLM 非依存・決定論・冪等。

生成結果は既存カタログ形状に厳密一致する:

事業部プラグイン（``config/division_plugins.yaml`` の各要素）::

    {id, label, category, description,
     department: {name, type, mission,
                  teams: [{name, mission, required_skills: [..]}]}}

会社プラグイン manifest（``config/company_plugins.yaml`` の各要素）::

    {id, label, genre, description,
     initial_kpis: [..], weekly_review: str, human_tasks: [..],
     divisions: [事業部名..]}

``type`` は ``DivisionType`` の値、``required_skills`` は ``AgentSkill`` の値。
これらは ``core.org_factory._build_division`` がそのまま食べられる dict であり、
``SpecialistAgent.skills`` の min 2 / max 3 制約も満たすよう各プリセットは
required_skills を 2 個ちょうどで持つ。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# --- §6.2 カテゴリ別プリセット --------------------------------------------------
#
# 各カテゴリ → 既定の DivisionType 値（``division_type``）と、
# その事業部に既定で置くチーム定義（``teams``: name / mission / required_skills）、
# および会社プラグインで divisions 未指定時に使う既定の事業部名（``default_divisions``）。
#
# required_skills はすべて AgentSkill の値で、各チーム 2 個ちょうど
# （SpecialistAgent.skills の min 2 / max 3 を満たし、_build_division で組み立て可能）。
#
# full_funnel は audience + monetization を合成するため、ここでは個別プリセットを
# 定義せず ``scaffold_division_plugin`` 内で両カテゴリの teams を連結する。

CATEGORY_PRESETS: Dict[str, Dict[str, Any]] = {
    "audience": {
        "division_type": "audience_development",
        "teams": [
            {
                "name": "Growth Team",
                "mission": "フォロワー獲得・エンゲージメント・送客導線",
                "required_skills": ["audience_growth", "performance_marketing"],
            },
            {
                "name": "Audience Content Team",
                "mission": "集客用コンテンツの企画制作",
                "required_skills": ["content_strategy", "audience_growth"],
            },
        ],
        "default_divisions": ["集客事業部", "コンテンツ制作事業部"],
    },
    "monetization": {
        "division_type": "monetization",
        "teams": [
            {
                "name": "Sales Writing Team",
                "mission": "収益化コンテンツのセールスライティングと構成",
                "required_skills": ["content_strategy", "performance_marketing"],
            },
            {
                "name": "Pricing Team",
                "mission": "価格設計・A/Bテスト・客単価最適化",
                "required_skills": ["performance_analysis", "performance_marketing"],
            },
        ],
        "default_divisions": ["収益化事業部", "分析・運用事業部"],
    },
    "full_funnel": {
        # audience + monetization を合成（teams は scaffold 側で連結）。
        "division_type": "audience_development",
        "teams": [],
        "default_divisions": [
            "集客事業部",
            "コンテンツ制作事業部",
            "収益化事業部",
            "分析・運用事業部",
        ],
    },
    "operations": {
        "division_type": "org_evolution",
        "teams": [
            {
                "name": "Analytics Team",
                "mission": "KPI 分析・レポート自動生成・改善提案",
                "required_skills": ["performance_analysis", "deep_research"],
            },
            {
                "name": "Planning Team",
                "mission": "全体最適のための戦略立案と調査",
                "required_skills": ["strategic_planning", "deep_research"],
            },
        ],
        "default_divisions": ["分析・運用事業部"],
    },
    "content": {
        "division_type": "content_production",
        "teams": [
            {
                "name": "Editorial Team",
                "mission": "記事・台本・概要欄の制作と品質管理",
                "required_skills": ["content_strategy", "knowledge_curation"],
            },
            {
                "name": "Research Team",
                "mission": "テーマ設計のためのリサーチと知識整理",
                "required_skills": ["deep_research", "knowledge_curation"],
            },
        ],
        "default_divisions": ["コンテンツ制作事業部"],
    },
}

# 未知カテゴリのフォールバック先（§6.2）。
_DEFAULT_CATEGORY = "operations"


def _resolve_category(category: Optional[str]) -> str:
    """カテゴリ名を CATEGORY_PRESETS のキーへ解決する。未知/None は operations 扱い。"""
    key = str(category or "").strip().lower()
    return key if key in CATEGORY_PRESETS else _DEFAULT_CATEGORY


def _preset_teams(category: str) -> List[Dict[str, Any]]:
    """カテゴリの teams を返す（full_funnel は audience+monetization を合成）。

    返す dict はプリセットのコピー（呼び出し側の変更が定数へ波及しない＝冪等・決定論）。
    """
    if category == "full_funnel":
        merged: List[Dict[str, Any]] = []
        for sub in ("audience", "monetization"):
            merged.extend(_copy_teams(CATEGORY_PRESETS[sub]["teams"]))
        return merged
    return _copy_teams(CATEGORY_PRESETS[category]["teams"])


def _copy_teams(teams: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """teams プリセットを deep-ish copy する（required_skills のリストも複製）。"""
    return [
        {
            "name": team["name"],
            "mission": team["mission"],
            "required_skills": list(team["required_skills"]),
        }
        for team in teams
    ]


def self_improvement_seed_division() -> Dict[str, Any]:
    """全テンプレ共通の「自己改善シード」事業部の department dict を返す（TPL-SEED / §6.2）。

    会社プラグイン install 時に各社へ標準搭載する、週次/月次の自己レビュー Agent を持つ
    事業部（``org_evolution`` 型）。このレビュー Agent が実行されると WIRE-MEM 経由で成功施策が
    Playbook に自動蓄積され、AUTO-1 の HQ cadence が弱みを Meta-Overseer へエスカレーションする。
    つまり §6.2「週次レビュー Agent + Playbook 自動蓄積 + エスカレーション」を 1 事業部で満たす。

    ``_build_division`` がそのまま食べられる形（required_skills は 2 個ちょうど）。
    """
    return {
        "name": "改善・自己レビュー事業部",
        "type": "org_evolution",
        "mission": "週次/月次で成果を振り返り、学びを Playbook 化して次の施策へ反映する",
        "teams": [
            {
                "name": "Weekly Review Team",
                "mission": "KPI レビュー・うまくいった施策の言語化・改善提案のエスカレーション",
                "required_skills": ["performance_analysis", "strategic_planning"],
            },
        ],
    }


def scaffold_division_plugin(
    plugin_id: str,
    label: str,
    category: str,
    *,
    description: str = "",
    mission: str = "",
) -> Dict[str, Any]:
    """事業部プラグインの雛形 dict を生成する（``division_plugins.yaml`` 要素と同形）。

    カテゴリプリセット（``CATEGORY_PRESETS``）から ``department`` を組み立てる。
    未知カテゴリは ``operations`` 扱い。``full_funnel`` は audience + monetization の
    teams を合成する（チーム数 = 4）。

    返却形状::

        {id, label, category, description,
         department: {name, type, mission,
                      teams: [{name, mission, required_skills}]}}

    生成は決定論・冪等で LLM 非依存。``department`` は ``_build_division`` がそのまま
    食べられる（各チームの required_skills は 2 個ちょうど）。
    """
    resolved = _resolve_category(category)
    preset = CATEGORY_PRESETS[resolved]

    dept_name = str(label).strip() or str(plugin_id)
    dept_mission = str(mission).strip() or f"{dept_name}の業務を担う"
    desc = str(description).strip() or f"{dept_name}（{resolved} カテゴリの事業部プラグイン）"

    department: Dict[str, Any] = {
        "name": dept_name,
        "type": preset["division_type"],
        "mission": dept_mission,
        "teams": _preset_teams(resolved),
    }
    return {
        "id": str(plugin_id),
        "label": str(label),
        "category": resolved,
        "description": desc,
        "department": department,
    }


def scaffold_company_plugin(
    plugin_id: str,
    label: str,
    genre: str,
    *,
    divisions: Optional[List[str]] = None,
    category: Optional[str] = None,
    initial_kpis: Optional[List[str]] = None,
    human_tasks: Optional[List[str]] = None,
    weekly_review: str = "",
) -> Dict[str, Any]:
    """会社プラグイン manifest の雛形 dict を生成する（``company_plugins.yaml`` 要素と同形）。

    ``divisions`` 未指定なら ``category`` のプリセット（``default_divisions``）から
    既定の事業部名リストを与える（``category`` も未知/None なら operations 扱い）。

    返却形状::

        {id, label, genre, description,
         initial_kpis: [..], weekly_review: str, human_tasks: [..],
         divisions: [事業部名..]}

    生成は決定論・冪等で LLM 非依存。``divisions`` の各名称は
    ``install_company_plugin`` 側の ``_division_spec_from_name`` で型/スキル推定され、
    そのまま会社を起動できる。
    """
    resolved = _resolve_category(category)

    if divisions is not None:
        division_names = [str(d).strip() for d in divisions if str(d).strip()]
    else:
        division_names = list(CATEGORY_PRESETS[resolved]["default_divisions"])

    company_label = str(label).strip() or str(plugin_id)
    description = f"{company_label}（{genre} ジャンルの会社プラグイン）"

    return {
        "id": str(plugin_id),
        "label": str(label),
        "genre": str(genre),
        "description": description,
        "initial_kpis": [str(k) for k in (initial_kpis or [])],
        "weekly_review": str(weekly_review),
        "human_tasks": [str(t) for t in (human_tasks or [])],
        "divisions": division_names,
    }
