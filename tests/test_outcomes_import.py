"""
成果イベントの一括取り込み（OutcomeStore.record_many ＋ CLI hq outcomes import）の検証。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from commands.hq import cmd_hq_outcomes
from core.metrics.outcomes import OutcomeStore
from core.platform.state import PlatformStateManager


def test_summary_by_source_breakdown(tmp_path):
    """by_source が収益チャネル別に metric を内訳化する（finding 8）。"""
    store = OutcomeStore(platform_home=tmp_path)
    store.record("Note Sales", "revenue", 1000, source="note")
    store.record("Note Sales", "revenue", 400, source="affiliate")
    store.record("Note Sales", "clicks", 50, source="note")
    store.record("Note Sales", "revenue", 200)  # source 空 → "(unknown)"

    summary = store.summary_for_org("Note Sales")
    # 全体合算は従来どおり
    assert summary.by_metric["revenue"]["sum"] == 1600
    assert summary.total_revenue == 1600
    # チャネル別内訳
    assert summary.by_source["note"]["revenue"]["sum"] == 1000
    assert summary.by_source["note"]["clicks"]["sum"] == 50
    assert summary.by_source["affiliate"]["revenue"]["sum"] == 400
    assert summary.by_source["(unknown)"]["revenue"]["sum"] == 200


def test_outcome_actor_audit_fields(tmp_path):
    """record が actor/actor_type を保持し、旧 JSON（フィールド無し）も既定で読める（finding 26）。"""
    store = OutcomeStore(platform_home=tmp_path)
    store.record("Co", "revenue", 100, actor="web:manual", actor_type="manual")
    e = store.list_events("Co")[0]
    assert e.actor == "web:manual" and e.actor_type == "manual"

    # 旧スキーマ（actor 無し）レコードも例外なく読める＝後方互換
    import json

    store.outcomes_path.write_text(
        json.dumps([{"org_name": "Co", "metric": "revenue", "value": 5}]), encoding="utf-8"
    )
    legacy = store.list_events("Co")
    assert legacy[0].actor == "" and legacy[0].value == 5.0


def test_export_events_csv_filters_and_header(tmp_path):
    """export_events_csv が metric/日付で絞り、ヘッダ付き CSV を返す（finding 21）。"""
    store = OutcomeStore(platform_home=tmp_path)
    store.record("Co", "revenue", 1000, source="note", occurred_at="2026-01-10")
    store.record("Co", "revenue", 2000, source="note", occurred_at="2026-03-10")
    store.record("Co", "clicks", 50, occurred_at="2026-01-10")

    full = store.export_events_csv("Co")
    assert full.splitlines()[0].startswith("org_name,metric,value")
    assert len([ln for ln in full.splitlines() if ln]) == 4  # header + 3

    # metric フィルタ
    rev = store.export_events_csv("Co", metric="revenue")
    assert len([ln for ln in rev.splitlines() if ln]) == 3  # header + 2 revenue
    # 日付範囲（1月のみ）
    jan = store.export_events_csv(
        "Co", metric="revenue", start_date="2026-01-01", end_date="2026-01-31"
    )
    assert "1000" in jan and "2000" not in jan


def test_export_outcomes_api_not_shadowed_by_org_route(tmp_path, monkeypatch):
    """GET /api/outcomes/export が {org_name} ルートにシャドウされず CSV を返す（finding 21）。"""
    from fastapi.testclient import TestClient

    import web.server as server

    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    monkeypatch.setattr(server, "_psm", lambda: PlatformStateManager(platform_home=tmp_path))
    OutcomeStore(platform_home=tmp_path).record("Co", "revenue", 500, occurred_at="2026-01-10")

    resp = TestClient(server.app).get("/api/outcomes/export?org_name=Co")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "org_name,metric,value" in resp.text and "revenue" in resp.text


def test_record_many_imports_and_skips_invalid(tmp_path):
    store = OutcomeStore(platform_home=tmp_path)
    rows = [
        {"org_name": "Note Sales", "metric": "revenue", "value": 1000},
        {"org_name": "Note Sales", "metric": "sales", "value": "3"},  # 文字列でも float 化
        {"metric": "clicks", "value": 50},  # org 欠落 → default_org で補完
        {"org_name": "X", "metric": "", "value": 1},  # metric 欠落 → skip
        {"org_name": "X", "metric": "revenue", "value": "abc"},  # value 不正 → skip
    ]
    added, skipped = store.record_many(rows, default_org="Note Sales")
    assert len(added) == 3
    assert skipped == 2
    summary = store.summary_for_org("Note Sales")
    assert summary.by_metric["revenue"]["sum"] == 1000
    assert summary.by_metric["sales"]["sum"] == 3
    assert summary.by_metric["clicks"]["sum"] == 50


def test_cli_import_csv(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    psm = PlatformStateManager(platform_home=tmp_path)
    csv_path = tmp_path / "outcomes.csv"
    csv_path.write_text(
        "org_name,metric,value,source\n"
        "Note Sales,revenue,5000,note-dashboard\n"
        "SNS Growth,impressions,12000,x-analytics\n",
        encoding="utf-8",
    )
    asyncio.run(
        cmd_hq_outcomes(
            SimpleNamespace(outcomes_action="import", path=str(csv_path), org_name=""),
            get_psm=lambda: psm,
        )
    )
    out = capsys.readouterr().out
    assert "2 件取り込みました" in out
    store = OutcomeStore(platform_home=tmp_path)
    assert store.summary_for_org("Note Sales").total_revenue == 5000
    assert store.summary_for_org("SNS Growth").total_reach == 12000


def test_cli_import_json_with_default_org(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    psm = PlatformStateManager(platform_home=tmp_path)
    json_path = tmp_path / "outcomes.json"
    json_path.write_text(
        '[{"metric": "conversions", "value": 7}, {"metric": "revenue", "value": 2100}]',
        encoding="utf-8",
    )
    asyncio.run(
        cmd_hq_outcomes(
            SimpleNamespace(outcomes_action="import", path=str(json_path), org_name="Note Sales"),
            get_psm=lambda: psm,
        )
    )
    out = capsys.readouterr().out
    assert "2 件取り込みました" in out
    store = OutcomeStore(platform_home=tmp_path)
    summary = store.summary_for_org("Note Sales")
    assert summary.by_metric["conversions"]["sum"] == 7
    assert summary.by_metric["revenue"]["sum"] == 2100
