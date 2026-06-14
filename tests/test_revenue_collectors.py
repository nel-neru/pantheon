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
    """既定アダプタ（note/x/asp）は資格情報未接続なので収集 0・接続タスクを起票する。"""
    home = _home(tmp_path, monkeypatch)
    result = run_revenue_collection(platform_home=home)
    assert result["recorded"] == 0
    assert set(result["needs_connection"]) == {"note", "x", "asp"}
