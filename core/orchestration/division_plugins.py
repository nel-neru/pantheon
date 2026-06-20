"""2階層プラグインの「事業部（Division）」側。

`config/division_plugins.yaml` のカタログを読み、既存 Organization へ事業部を追加する。
構造の組み立ては `core.org_factory._build_division`（org 量産でも使う部品）を再利用し、
新しい構造は導入しない（Master Plan §13-4 / §13-3「共有は極力避ける」）。

会社（Company）側のプラグインは新規 org 量産（`pantheon org create --genre`）が相当機能。
ここでは `config/departments/*.yaml` を会社アーキタイプとして列挙する薄いカタログも提供する
（manifest の正式化は段階的な次ステップ。docs/plans/two-tier-plugin-marketplace-kickoff.md）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import yaml

from core.models.organization import Division, Organization
from core.org_factory import _build_division
from core.paths import resource_path

logger = logging.getLogger(__name__)

DIVISION_PLUGINS_FILE = "division_plugins.yaml"
DEPARTMENTS_DIR = "departments"


def _expand_plugin_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """カタログ 1 エントリを正規化する（テンプレ形なら department をプリセットで補完）。

    PT-2: ``department`` を持たず ``category`` だけのコンパクトな「テンプレ形」エントリは
    ``scaffold_division_plugin`` で department を生成して充足する（id+label+category だけで
    §6.2 カテゴリプリセットから事業部が組み上がる＝「テンプレ化」）。``department`` が既に
    ある従来エントリはそのまま返す（後方互換）。
    """
    if isinstance(entry.get("department"), dict):
        return entry
    from core.orchestration.plugin_templates import scaffold_division_plugin

    return scaffold_division_plugin(
        str(entry.get("id")),
        str(entry.get("label") or entry.get("id")),
        str(entry.get("category") or ""),
        description=str(entry.get("description") or ""),
        mission=str(entry.get("mission") or ""),
    )


def load_division_plugins() -> List[Dict[str, Any]]:
    """事業部プラグインのカタログを返す（欠落・破損時は空リスト＝GUI/CLI を壊さない）。

    ``department`` を持たない「テンプレ形」エントリは ``category`` のプリセットから
    自動展開する（PT-2）。
    """
    path = resource_path("config", DIVISION_PLUGINS_FILE)
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError) as exc:
        logger.warning("division_plugins.yaml の読み込みに失敗: %s", exc)
        return []
    plugins = data.get("plugins", [])
    return [_expand_plugin_entry(p) for p in plugins if isinstance(p, dict) and p.get("id")]


def get_division_plugin(plugin_id: str) -> Optional[Dict[str, Any]]:
    """id で 1 つの事業部プラグインを取得する。無ければ None。"""
    for plugin in load_division_plugins():
        if plugin.get("id") == plugin_id:
            return plugin
    return None


def add_division_plugin(org: Organization, plugin_id: str) -> Division:
    """事業部プラグインを Organization に追加し、追加した Division を返す。

    既存の `_build_division` で department dict から Division（Team + SpecialistAgent）を
    組み立て、`org.add_division` で取り付ける（呼び出し側で save すること）。
    未知の plugin_id / department 欠落は ValueError。
    """
    plugin = get_division_plugin(plugin_id)
    if plugin is None:
        raise ValueError(f"未知の事業部プラグインです: {plugin_id}")
    department = plugin.get("department")
    if not isinstance(department, dict):
        raise ValueError(f"事業部プラグイン '{plugin_id}' に department 定義がありません")
    division = _build_division(department)
    org.add_division(division)
    return division


def load_company_archetypes() -> List[Dict[str, Any]]:
    """会社「アーキタイプ」を `config/departments/*.yaml` から列挙する（install 不可・参考表示用）。

    各 yaml を id（ファイル名）/ label / 部門数で表現する薄いカタログ。これは
    `pantheon org create --genre` 用の参考アーキタイプであり、**`install-company` で起動できる
    会社プラグイン（manifest）とは別物**である（install できるのは
    ``core.orchestration.company_plugins.load_company_plugin_manifests`` の方）。
    両者を混同させない（list したものが install できないという footgun を避ける）ため、
    `plugin list` / GET /api/company-plugins は manifest を主に見せ、本関数はアーキタイプ参照に限る。
    """
    out: List[Dict[str, Any]] = []
    departments_dir = resource_path("config", DEPARTMENTS_DIR)
    if not departments_dir.is_dir():
        return out
    for path in sorted(departments_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError):
            continue
        departments = data.get("departments", []) if isinstance(data, dict) else []
        meta = data.get("meta", {}) if isinstance(data.get("meta"), dict) else {}
        out.append(
            {
                "id": path.stem,
                "label": meta.get("label") or path.stem,
                "division_count": len(departments),
                "divisions": [d.get("name", "") for d in departments if isinstance(d, dict)],
            }
        )
    return out
