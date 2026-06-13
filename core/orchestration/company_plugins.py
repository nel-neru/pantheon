"""会社（Company）プラグインの manifest ローダ（P2.2）。

2階層プラグイン構想の「会社」側を、宣言的な manifest カタログ
（``config/company_plugins.yaml``）として読み込む。各 manifest は
「収益化テンプレートとしての会社」を GUI/CLI に提示するためのメタデータであり、
構造（Division/Team/SpecialistAgent）そのものは持たない（実体の組み立ては
``pantheon org create --genre`` 等の既存量産経路が担当する）。

注: ``core.orchestration.division_plugins.load_company_plugins`` は
``config/departments/*.yaml`` を列挙する薄いアーキタイプ用で、本モジュールとは別物
（同ファイルが「manifest の正式化は段階的な次ステップ」と明記している、その次ステップ）。

堅牢性方針（``load_division_plugins`` に倣う）: 欠落・破損時は空リストを返して
生成パイプラインを止めない。``id`` を持つ dict 要素のみ返す。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.paths import resource_path

logger = logging.getLogger(__name__)

# 同梱カタログのファイル名（config/ 配下）。
COMPANY_PLUGINS_FILE = "company_plugins.yaml"


def _default_catalog_path() -> Path:
    """同梱の会社プラグイン manifest カタログへの絶対パスを返す。"""
    return resource_path("config", COMPANY_PLUGINS_FILE)


def load_company_plugin_manifests(
    catalog_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """会社プラグインの manifest 一覧を返す。

    ``config/company_plugins.yaml``（``catalog_path`` 省略時は
    ``resource_path('config', 'company_plugins.yaml')``）を読み、``id`` を持つ
    dict 要素のみを返す。欠落・破損・想定外の構造はすべて空リストにフォールバックし、
    呼び出し側（GUI/CLI/量産）の生成を止めない。

    ``catalog_path`` は主にテストの ``tmp_path`` 注入用（``OutcomeStore`` の
    ``platform_home`` 注入と同じ思想）。本番では省略して同梱カタログを読む。
    """
    path = Path(catalog_path) if catalog_path is not None else _default_catalog_path()
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError) as exc:
        logger.warning("company_plugins.yaml の読み込みに失敗: %s", exc)
        return []
    if not isinstance(data, dict):
        # トップレベルが dict でない（リスト/スカラ等）壊れたカタログは無視する。
        return []
    plugins = data.get("plugins", [])
    if not isinstance(plugins, list):
        return []
    return [p for p in plugins if isinstance(p, dict) and p.get("id")]


def get_company_plugin_manifest(
    plugin_id: str,
    catalog_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """``id`` で 1 つの会社プラグイン manifest を取得する。無ければ ``None``。"""
    for manifest in load_company_plugin_manifests(catalog_path=catalog_path):
        if manifest.get("id") == plugin_id:
            return manifest
    return None


# 事業部名のキーワード → (DivisionType 値, 既定スキル) の推定表（P2.2b install 用）。
_DIVISION_KEYWORDS = (
    (
        ("販売", "収益", "マーケ", "アフィ", "送客", "monetiz"),
        "monetization",
        ["content_strategy", "performance_marketing"],
    ),
    (
        ("集客", "sns", "流入", "seo", "audience", "獲得"),
        "audience_development",
        ["audience_growth", "content_strategy"],
    ),
    (
        ("制作", "企画", "記事", "コンテンツ", "編集", "投稿", "content"),
        "content_production",
        ["content_strategy", "knowledge_curation"],
    ),
)


def _division_spec_from_name(name: str) -> Dict[str, Any]:
    """事業部名から org_factory._build_division 用の department dict を合成する（型/スキルを推定）。"""
    lowered = str(name).lower()
    div_type = "org_evolution"
    skills = ["strategic_planning", "deep_research"]
    for keywords, mapped_type, mapped_skills in _DIVISION_KEYWORDS:
        if any(k in lowered for k in keywords):
            div_type, skills = mapped_type, mapped_skills
            break
    return {
        "name": name,
        "type": div_type,
        "mission": f"{name}の業務を担う",
        "teams": [{"name": f"{name} Team", "mission": f"{name}の実務", "required_skills": skills}],
    }


def install_company_plugin(
    plugin_id: str,
    *,
    psm: Any,
    name: Optional[str] = None,
    repo_path: Optional[str] = None,
    catalog_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """会社プラグイン manifest から **完全な Organization を起動**する（P2.2b 本丸）。

    manifest の divisions（名称）から Division/Team/SpecialistAgent を組み立て、
    人間専用タスク（human_tasks）を承認キューへ積み、初期KPIをメタに残して保存する。
    収益モデル会社が「プラグインを足すだけで丸ごと立ち上がる」体験を実現する（§7.1）。

    未知 plugin_id / 同名 org 既存は ValueError。``psm`` は PlatformStateManager。
    """
    from core.humans.human_tasks import enqueue_human_task
    from core.models.organization import Organization, OrganizationStatus
    from core.org_factory import _build_division

    manifest = get_company_plugin_manifest(plugin_id, catalog_path=catalog_path)
    if manifest is None:
        raise ValueError(f"未知の会社プラグインです: {plugin_id}")

    org_name = (name or manifest.get("label") or plugin_id).strip()
    if psm.load_organization_by_name(org_name):
        raise ValueError(f"Organization '{org_name}' はすでに存在します")

    # Workspace モデル（§5）: 収益モデル会社は **git ではなくアプリ内データ領域**で管理する。
    # repo_path 明示時はそれをデータ領域に、未指定なら workspaces_root 配下に作る（git init はしない）。
    if repo_path:
        ws = Path(repo_path)
    else:
        import re

        root = getattr(psm, "get_workspaces_root", lambda: None)() or (
            psm.platform_home / "workspaces"
        )
        safe = re.sub(r"[^A-Za-z0-9_-]+", "-", org_name).strip("-") or "company"
        ws = Path(root) / safe
    try:
        ws.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    purpose = str(manifest.get("description") or "").strip() or f"{org_name}（会社プラグイン）"
    org = Organization(
        name=org_name,
        purpose=purpose,
        management_mode="workspace",
        workspace_path=str(ws),
        status=OrganizationStatus.INCUBATING,
        isolation_level="external",
    )
    genre = manifest.get("genre")
    if genre:
        org.industry_genre = str(genre)

    division_names = [d for d in (manifest.get("divisions") or []) if str(d).strip()]
    for div_name in division_names:
        org.add_division(_build_division(_division_spec_from_name(str(div_name))))

    psm.save_organization(org)

    # 人間専用タスク（初期設定）を承認キューへ積む。
    human_tasks = [str(t).strip() for t in (manifest.get("human_tasks") or []) if str(t).strip()]
    for task in human_tasks:
        enqueue_human_task(
            f"{org_name}: {task}",
            platform_home=psm.platform_home,
            kind="company_setup",
            org_name=org_name,
            dedupe_key=f"company_setup:{org_name}:{task}",
        )

    agents = org.get_all_agents()
    return {
        "ok": True,
        "org_name": org.name,
        "genre": getattr(org, "industry_genre", None),
        "divisions": [d.name for d in org.divisions],
        "agent_count": len(agents),
        "human_tasks_created": len(human_tasks),
        "initial_kpis": list(manifest.get("initial_kpis") or []),
        "management_mode": org.management_mode,
        "workspace_path": org.workspace_path,
    }
