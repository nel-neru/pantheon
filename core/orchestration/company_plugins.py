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
