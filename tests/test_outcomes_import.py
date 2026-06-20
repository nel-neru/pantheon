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
