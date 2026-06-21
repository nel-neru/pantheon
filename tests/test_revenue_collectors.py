"""REV-COLLECT: 収益自動収集フレームワークのテスト（決定論・冪等・LLM 非依存）。

実 API 認証は human-gate のため、ここでは枠組み（接続判定・記録・接続タスク起票・冪等）を検証する。
注入したフェイクコレクタで「接続済み→記録」「未接続→接続タスク一度きり」を確認する。
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from core.humans.human_tasks import HumanTaskStore
from core.metrics.outcomes import OutcomeStore
from core.metrics.revenue_collectors import run_revenue_collection
from core.metrics.revenue_collectors.base import CollectedRevenue, RevenueCollector


class _ConfiguredCollector(RevenueCollector):
    source = "fake_note"
    label = "Fake note"

    def is_configured(self, platform_home: Path) -> bool:
        return True

    def fetch(self, platform_home: Path) -> List[CollectedRevenue]:
        return [
            CollectedRevenue(
                org_name="Note Co",
                amount=1200.0,
                source="fake_note:2026-06:art1",
                occurred_at="2026-06-10",
            )
        ]


class _UnconfiguredCollector(RevenueCollector):
    source = "fake_x"
    label = "Fake X"

    def is_configured(self, platform_home: Path) -> bool:
        return False

    def fetch(self, platform_home: Path) -> List[CollectedRevenue]:  # pragma: no cover
        raise AssertionError("未接続コレクタの fetch は呼ばれてはならない")


def _home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: home)
    return home


def test_configured_collector_records_revenue(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    result = run_revenue_collection(platform_home=home, collectors=[_ConfiguredCollector()])

    assert result["recorded"] == 1
    assert result["collected_sources"] == ["fake_note"]
    summary = OutcomeStore(platform_home=home).summary_for_org("Note Co")
    assert summary.total_revenue == 1200.0


def test_unconfigured_collector_enqueues_connect_task_once(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    collector = _UnconfiguredCollector()

    first = run_revenue_collection(platform_home=home, collectors=[collector])
    assert first["recorded"] == 0
    assert first["needs_connection"] == ["fake_x"]

    # 冪等: 再実行しても接続タスクは増えない（dedupe_key）。
    run_revenue_collection(platform_home=home, collectors=[collector])
    tasks = [
        t for t in HumanTaskStore(platform_home=home).list_tasks() if t.kind == "revenue_connect"
    ]
    assert len(tasks) == 1


def test_collection_is_idempotent_by_source(tmp_path, monkeypatch):
    """同一 source のレコードは dedupe_on_source で二重計上されない。"""
    home = _home(tmp_path, monkeypatch)
    run_revenue_collection(platform_home=home, collectors=[_ConfiguredCollector()])
    run_revenue_collection(platform_home=home, collectors=[_ConfiguredCollector()])

    summary = OutcomeStore(platform_home=home).summary_for_org("Note Co")
    assert summary.total_revenue == 1200.0  # 2 回走っても 1 件分のまま


def test_default_collectors_unconfigured_by_default(tmp_path, monkeypatch):
    """既定アダプタ（note/x/asp/youtube）は資格情報未接続なので収集 0・接続タスクを起票する。"""
    home = _home(tmp_path, monkeypatch)
    result = run_revenue_collection(platform_home=home)
    assert result["recorded"] == 0
    assert set(result["needs_connection"]) == {"note", "x", "asp", "youtube"}


def test_csv_import_makes_source_configured_and_records(tmp_path, monkeypatch):
    """revenue_imports/<source>.csv を置くと CSV から収益を自動収集する（P15）。"""
    home = _home(tmp_path, monkeypatch)
    csv_dir = home / "revenue_imports"
    csv_dir.mkdir(parents=True, exist_ok=True)
    (csv_dir / "note.csv").write_text(
        "org_name,amount,occurred_at,id\n"
        "Note Co,1200,2026-06-10,art1\n"
        "Note Co,800,2026-06-20,art2\n"
        ",999,2026-06-21,bad\n",  # org 欠落 → skip
        encoding="utf-8",
    )
    result = run_revenue_collection(platform_home=home)
    assert result["recorded"] == 2  # 不正 1 行は skip
    assert "note" in result["collected_sources"]
    # x/asp/youtube は未接続のまま接続タスク対象
    assert set(result["needs_connection"]) == {"x", "asp", "youtube"}
    summary = OutcomeStore(platform_home=home).summary_for_org("Note Co")
    assert summary.total_revenue == 2000.0

    # 冪等: 同じ CSV を再取り込みしても二重計上しない（dedupe_on_source）。
    run_revenue_collection(platform_home=home)
    assert OutcomeStore(platform_home=home).summary_for_org("Note Co").total_revenue == 2000.0


def test_youtube_csv_records_confirmed_revenue(tmp_path, monkeypatch):
    """revenue_imports/youtube.csv を置くと YouTube 収益が確定収益として記録される。"""
    from core.metrics.revenue_integrity import assess_revenue_integrity

    home = _home(tmp_path, monkeypatch)
    csv_dir = home / "revenue_imports"
    csv_dir.mkdir(parents=True, exist_ok=True)
    (csv_dir / "youtube.csv").write_text(
        "org_name,amount,occurred_at,id\nRedThread,3500,2026-06-15,ads1\n",
        encoding="utf-8",
    )
    result = run_revenue_collection(platform_home=home)
    assert "youtube" in result["collected_sources"]
    store = OutcomeStore(platform_home=home)
    integ = assess_revenue_integrity(store)
    assert integ["confirmed_revenue"] == 3500.0  # 確定収益（実CSV由来）
    assert "youtube" in {s.split(":")[0] for s in integ["confirmed_sources"]}


def test_parse_revenue_csv_skips_malformed_without_raising(tmp_path):
    """壊れた行は例外を投げず skip する（silent-drop-observability）。"""
    from core.metrics.revenue_collectors.csv_import import parse_revenue_csv

    path = tmp_path / "asp.csv"
    path.write_text("org_name,amount\nCo,not-a-number\nCo,500\n", encoding="utf-8")
    records = parse_revenue_csv(path, "asp")
    assert len(records) == 1 and records[0].amount == 500.0
    assert records[0].source.startswith("asp:")
