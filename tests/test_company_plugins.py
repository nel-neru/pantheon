"""会社プラグイン manifest ローダ（P2.2）のテスト。

- 同梱カタログ（config/company_plugins.yaml）に既知 id が含まれること
- 各 manifest が divisions / initial_kpis を持つこと
- get_company_plugin_manifest が既知 id を返し、未知 id では None
- tmp_path 注入で読み込み/スキップ/フォールバックが期待どおりに振る舞うこと

ストア系の規約に倣い、tmp_path 注入テストは get_platform_home に依存せず
catalog_path 引数で yaml を直接渡す。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.orchestration.company_plugins import (
    get_company_plugin_manifest,
    install_company_plugin,
    load_company_plugin_manifests,
)


def _injected_catalog(tmp_path):
    path = tmp_path / "company_plugins.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "plugins": [
                    {
                        "id": "note_co",
                        "label": "note販売会社",
                        "genre": "digital_content",
                        "description": "note で有料記事を販売する会社",
                        "divisions": ["コンテンツ企画部", "販売・マーケティング部"],
                        "human_tasks": ["有料記事の公開承認", "価格設定"],
                        "initial_kpis": ["有料記事の売上"],
                    }
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return path


def test_install_company_plugin_creates_full_org(tmp_path):
    """会社プラグイン install で org + 事業部 + Humanタスクが起動する（P2.2b）。"""
    from core.humans.human_tasks import HumanTaskStore
    from core.platform.state import PlatformStateManager

    catalog = _injected_catalog(tmp_path)
    psm = PlatformStateManager(platform_home=tmp_path)
    result = install_company_plugin("note_co", psm=psm, catalog_path=catalog)

    assert result["ok"] is True
    assert result["org_name"] == "note販売会社"
    assert "コンテンツ企画部" in result["divisions"]
    assert "販売・マーケティング部" in result["divisions"]
    assert result["human_tasks_created"] == 2
    assert result["initial_kpis"] == ["有料記事の売上"]
    # Workspace モデル（§5）: git repo ではなくアプリ内データ領域で管理される。
    assert result["management_mode"] == "workspace"
    assert result["workspace_path"]

    org = psm.load_organization_by_name("note販売会社")
    # manifest の 2 事業部 + TPL-SEED の「改善・自己レビュー事業部」= 3
    assert org is not None and len(org.divisions) == 3
    assert "改善・自己レビュー事業部" in {d.name for d in org.divisions}
    # 初期KPI が org に永続化される（KPI ダッシュボードの元データ・TPL-SEED §6.1）
    assert org.initial_kpis == ["有料記事の売上"]
    assert org.get_all_agents()  # 各事業部に Specialist が生成される
    # workspace モード: git 不要・target_repo_path 無し・データ位置は workspace_path。
    assert org.management_mode == "workspace"
    assert org.target_repo_path is None
    assert org.is_workspace_bound is False  # git repo は持たない
    assert org.is_managed is True and org.data_location == org.workspace_path
    # 事業部名から type 推定（販売→monetization）
    types = {d.name: d.type.value for d in org.divisions}
    assert types["販売・マーケティング部"] == "monetization"

    tasks = HumanTaskStore(platform_home=tmp_path).list_tasks("open")
    assert [t for t in tasks if t.kind == "company_setup" and t.org_name == "note販売会社"]


def test_install_unknown_plugin_raises(tmp_path):
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home=tmp_path)
    with pytest.raises(ValueError):
        install_company_plugin("nope", psm=psm, catalog_path=tmp_path / "missing.yaml")


def test_install_duplicate_org_raises(tmp_path):
    from core.platform.state import PlatformStateManager

    catalog = _injected_catalog(tmp_path)
    psm = PlatformStateManager(platform_home=tmp_path)
    install_company_plugin("note_co", psm=psm, catalog_path=catalog)
    with pytest.raises(ValueError):
        install_company_plugin("note_co", psm=psm, catalog_path=catalog)


# 同梱カタログに必ず存在すると保証する既知 id。
KNOWN_IDS = ("note_sales", "affiliate", "sns_growth")

# manifest が宣言すべき必須キー。
REQUIRED_KEYS = (
    "id",
    "label",
    "genre",
    "description",
    "initial_kpis",
    "weekly_review",
    "human_tasks",
    "divisions",
)


class TestBundledCatalog:
    def test_catalog_contains_known_ids(self):
        manifests = load_company_plugin_manifests()
        ids = {m["id"] for m in manifests}
        for known in KNOWN_IDS:
            assert known in ids, f"既知の会社プラグイン id が欠落: {known}"

    def test_each_manifest_has_divisions_and_kpis(self):
        for manifest in load_company_plugin_manifests():
            divisions = manifest.get("divisions")
            kpis = manifest.get("initial_kpis")
            assert isinstance(divisions, list) and divisions, (
                f"{manifest.get('id')!r} に divisions がありません"
            )
            assert isinstance(kpis, list) and kpis, (
                f"{manifest.get('id')!r} に initial_kpis がありません"
            )

    def test_each_manifest_has_required_keys(self):
        for manifest in load_company_plugin_manifests():
            for key in REQUIRED_KEYS:
                assert key in manifest, f"{manifest.get('id')!r} に必須キー {key} がありません"

    def test_get_known_manifest_returns_dict(self):
        manifest = get_company_plugin_manifest("note_sales")
        assert manifest is not None
        assert manifest["id"] == "note_sales"
        assert manifest.get("divisions")

    def test_get_unknown_manifest_returns_none(self):
        assert get_company_plugin_manifest("no_such_company_xyz") is None


class TestCatalogPathInjection:
    def _write(self, tmp_path, payload):
        path = tmp_path / "company_plugins.yaml"
        path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
        return path

    def test_loads_injected_catalog(self, tmp_path):
        path = self._write(
            tmp_path,
            {
                "plugins": [
                    {"id": "custom_co", "label": "カスタム会社", "divisions": ["企画部"]},
                ]
            },
        )
        manifests = load_company_plugin_manifests(catalog_path=path)
        assert len(manifests) == 1
        assert manifests[0]["id"] == "custom_co"
        assert get_company_plugin_manifest("custom_co", catalog_path=path) is not None

    def test_skips_entries_without_id(self, tmp_path):
        path = self._write(
            tmp_path,
            {
                "plugins": [
                    {"id": "with_id", "label": "あり"},
                    {"label": "id なしはスキップ"},
                    "文字列要素も無視",
                ]
            },
        )
        manifests = load_company_plugin_manifests(catalog_path=path)
        assert [m["id"] for m in manifests] == ["with_id"]

    def test_missing_file_returns_empty(self, tmp_path):
        missing = tmp_path / "does_not_exist.yaml"
        assert load_company_plugin_manifests(catalog_path=missing) == []
        assert get_company_plugin_manifest("anything", catalog_path=missing) is None

    def test_malformed_yaml_returns_empty(self, tmp_path):
        path = tmp_path / "company_plugins.yaml"
        # 閉じていないフロー構文で yaml.YAMLError を誘発する。
        path.write_text("plugins: [unterminated\n", encoding="utf-8")
        assert load_company_plugin_manifests(catalog_path=path) == []

    def test_non_mapping_top_level_returns_empty(self, tmp_path):
        path = tmp_path / "company_plugins.yaml"
        # トップレベルがリスト（dict でない）壊れたカタログ。
        path.write_text("- just\n- a\n- list\n", encoding="utf-8")
        assert load_company_plugin_manifests(catalog_path=path) == []


def test_install_video_production_archetype(tmp_path):
    """新設した中立 video_production アーキタイプが external/workspace org を起動する。"""
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home=tmp_path)
    result = install_company_plugin("video_production", psm=psm)
    assert result["ok"] is True
    org = psm.load_organization_by_name(result["org_name"])
    assert org is not None
    assert org.isolation_level == "external"
    assert org.management_mode == "workspace"
    assert len(org.divisions) >= 1


def test_cli_install_company_wired():
    """会社プラグイン install が CLI からも叩ける（GUI 専用だった差を解消）。"""
    from commands import build_parser

    parser = build_parser()
    args = parser.parse_args(
        ["plugin", "install-company", "--id", "video_production", "--name", "VP"]
    )
    assert args.handler_name == "cmd_plugin_install_company"

    import main

    assert "cmd_plugin_install_company" in main.HANDLERS


def test_japanese_named_companies_get_distinct_workspaces(tmp_path):
    """非ASCII（日本語）名の会社を複数 install しても workspace が衝突しない（slug 一意化）。"""
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home=tmp_path)
    # video_production / affiliate は同梱の中立アーキタイプ（label が日本語）。
    r1 = install_company_plugin("video_production", psm=psm, name="動画制作社")
    r2 = install_company_plugin("affiliate", psm=psm, name="アフィリエイト社")

    assert r1["workspace_path"] and r2["workspace_path"]
    # かつて両方 ".../workspaces/company" に丸まって衝突していた箇所。
    assert r1["workspace_path"] != r2["workspace_path"]
    # 同名なら同一・安定（決定的ハッシュ）
    psm2 = PlatformStateManager(platform_home=tmp_path / "other")
    r3 = install_company_plugin("video_production", psm=psm2, name="動画制作社")
    assert Path(r3["workspace_path"]).name == Path(r1["workspace_path"]).name


def test_ascii_named_company_workspace_unchanged(tmp_path):
    """純ASCII名のワークスペース名は従来どおり（ハッシュ付与しない）。"""
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home=tmp_path)
    result = install_company_plugin("video_production", psm=psm, name="VideoCo")
    assert Path(result["workspace_path"]).name == "VideoCo"
