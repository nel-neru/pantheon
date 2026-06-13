"""会社プラグイン manifest ローダ（P2.2）のテスト。

- 同梱カタログ（config/company_plugins.yaml）に既知 id が含まれること
- 各 manifest が divisions / initial_kpis を持つこと
- get_company_plugin_manifest が既知 id を返し、未知 id では None
- tmp_path 注入で読み込み/スキップ/フォールバックが期待どおりに振る舞うこと

ストア系の規約に倣い、tmp_path 注入テストは get_platform_home に依存せず
catalog_path 引数で yaml を直接渡す。
"""

from __future__ import annotations

import yaml

from core.orchestration.company_plugins import (
    get_company_plugin_manifest,
    load_company_plugin_manifests,
)

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
