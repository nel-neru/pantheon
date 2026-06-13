"""RevenueScheduler（revenue daemon）の検証 — 決定論・LLM 非依存・承認ゲート遵守。

revenue daemon は他デーモンと違い ``claude`` を一切呼ばない純粋計算（収益分析＋
ポートフォリオ提案スキャン）なので、ここでも claude CLI を起動しない。検証点:

- idle（``target<=0``）: 収益分析は常に走るが提案スキャンはスキップ（``scan_skipped``・起票ゼロ）。
- active（``target>0``）: ポートフォリオ提案を承認ゲートへ起票（``proposed`` のみ・自動採用しない）。
- 冪等: 同条件で再実行しても二重起票しない。
- heartbeat: watchdog 用 heartbeat を毎ビート書く。
- 堅牢性: 収益分析が失敗してもサイクルは落ちない（握りつぶして続行）。
"""

from __future__ import annotations

import asyncio

from core.hierarchy.revenue_scheduler import RevenueScheduler
from core.metrics.outcomes import OutcomeStore
from core.org_factory import create_default_organization
from core.platform.state import PlatformStateManager
from core.runtime.heartbeat import read_heartbeat


def _home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: home)
    return home


def _proposals_for(psm: PlatformStateManager, org_name: str):
    org = psm.load_organization_by_name(org_name)
    return psm.get_org_state_manager(org).get_all_improvement_proposals()


def test_idle_runs_analysis_but_skips_proposals(tmp_path, monkeypatch):
    """target<=0 は org があっても一切起票しない（無人運転の安全な既定）。"""
    home = _home(tmp_path, monkeypatch)
    psm = PlatformStateManager(platform_home=home)
    psm.save_organization(create_default_organization("Reachy", "集客"))
    OutcomeStore(platform_home=home).record("Reachy", "impressions", 5000)

    sched = RevenueScheduler(platform_home=home, target=0.0)
    summary = asyncio.run(sched.run_cycle())

    assert summary["scan_skipped"] is True
    assert summary["proposals"] == 0
    assert summary["scanned"] == 0
    # 収益記録が無くても分析自体は走る（2 点未満なので insufficient）
    assert summary["trend"] == "insufficient"
    assert _proposals_for(psm, "Reachy") == []


def test_active_enqueues_approval_gated_proposals(tmp_path, monkeypatch):
    """target>0 は承認ゲートへ提案を起票するが、必ず proposed で止まる（自動採用しない）。"""
    home = _home(tmp_path, monkeypatch)
    psm = PlatformStateManager(platform_home=home)
    psm.save_organization(create_default_organization("Reachy", "集客"))
    OutcomeStore(platform_home=home).record("Reachy", "impressions", 5000)

    sched = RevenueScheduler(platform_home=home, target=100000.0)
    summary = asyncio.run(sched.run_cycle())

    assert summary["scan_skipped"] is False
    assert summary["proposals"] > 0
    assert summary["scanned"] >= summary["proposals"]
    proposals = _proposals_for(psm, "Reachy")
    assert proposals
    assert all(p["status"] == "proposed" for p in proposals)


def test_active_scan_is_idempotent_across_restarts(tmp_path, monkeypatch):
    """別プロセス相当（新インスタンス）で再スキャンしても二重起票しない。

    24/7 の冪等性は in-memory 状態ではなく永続化済み提案の dedupe_key に依存する。
    watchdog 再起動を模して 2 サイクル目を新しい RevenueScheduler で回す。
    """
    home = _home(tmp_path, monkeypatch)
    psm = PlatformStateManager(platform_home=home)
    psm.save_organization(create_default_organization("Reachy", "集客"))
    OutcomeStore(platform_home=home).record("Reachy", "impressions", 5000)

    first = asyncio.run(RevenueScheduler(platform_home=home, target=100000.0).run_cycle())
    assert first["proposals"] > 0
    # 別インスタンス = 再起動後。永続化された dedupe_key を読むので二重起票しない。
    second = asyncio.run(RevenueScheduler(platform_home=home, target=100000.0).run_cycle())
    assert second["proposals"] == 0


def test_run_cycle_writes_log_and_beats_heartbeat(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    sched = RevenueScheduler(platform_home=home, target=0.0)

    sched._beat("running")
    hb = read_heartbeat("revenue", platform_home=home)
    assert hb is not None
    assert hb["status"] == "running"

    asyncio.run(sched.run_cycle())
    logs = sched.get_recent_logs()
    assert logs
    assert logs[-1]["cycle"] == 1


def _boom(*_a, **_k):
    raise RuntimeError("boom")


def test_run_cycle_resilient_to_analysis_failure(tmp_path, monkeypatch):
    """収益分析が失敗してもサイクルは落ちずサマリを返す（観測可能な握りつぶし）。"""
    home = _home(tmp_path, monkeypatch)
    monkeypatch.setattr("core.metrics.revenue_intelligence.analyze_revenue", _boom)

    sched = RevenueScheduler(platform_home=home, target=0.0)
    summary = asyncio.run(sched.run_cycle())

    assert summary["cycle"] == 1
    assert summary["trend"] is None  # 分析失敗 → analysis 空のまま続行
