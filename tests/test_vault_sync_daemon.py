"""Tests for the Vault auto-sync daemon (Phase 4).

``VaultSyncScheduler.run_cycle`` does one bidirectional vault sync over a
``tmp_path`` platform home; heartbeat + cycle log are written; ``stop()`` halts
the loop; sync failures are recorded (not swallowed) without crashing.
"""

from __future__ import annotations

import asyncio

from core.runtime.heartbeat import read_heartbeat
from core.vault.sync_scheduler import VaultSyncScheduler


def test_run_cycle_syncs_and_logs(tmp_path):
    sched = VaultSyncScheduler(platform_home=tmp_path, interval_seconds=300)
    summary = asyncio.run(sched.run_cycle())

    assert summary["cycle"] == 1
    assert "error" not in summary
    # 双方向同期の両方向の集計キーが入る。
    assert "imported" in summary
    assert "exported" in summary
    assert "conflicts" in summary
    # vault ディレクトリが実体化される。
    assert (tmp_path / "vault").is_dir()
    # サイクルログが残る（母数の観測）。
    logs = sched.get_recent_logs()
    assert logs and logs[-1]["cycle"] == 1


def test_beat_writes_heartbeat(tmp_path):
    sched = VaultSyncScheduler(platform_home=tmp_path)
    sched._beat("running")
    beat = read_heartbeat("vault_sync", platform_home=tmp_path)
    assert beat is not None
    assert beat["status"] == "running"
    assert beat["interval_seconds"] == 300


def test_stop_halts_start_loop(tmp_path, monkeypatch):
    # 待機チャンクを詰めて stop() への応答をテスト時間内にする（本番は 60s チャンク）。
    monkeypatch.setattr("core.vault.sync_scheduler.SLEEP_CHUNK_SECONDS", 0.01)
    sched = VaultSyncScheduler(platform_home=tmp_path, interval_seconds=60)

    async def run_and_stop():
        task = asyncio.create_task(sched.start())
        await asyncio.sleep(0.05)
        sched.stop()
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(run_and_stop())
    assert sched._running is False
    beat = read_heartbeat("vault_sync", platform_home=tmp_path)
    assert beat is not None
    assert beat["status"] == "stopped"


def test_run_cycle_records_error_without_crashing(tmp_path, monkeypatch):
    """sync 失敗時もクラッシュせず error を log に残す（黙殺せず・次サイクル再試行）。"""
    sched = VaultSyncScheduler(platform_home=tmp_path)

    def _boom(*_a, **_k):
        raise RuntimeError("disk gone")

    monkeypatch.setattr("core.vault.build_default_sync", _boom)
    summary = asyncio.run(sched.run_cycle())
    assert summary["error"] == "disk gone"
    assert summary["cycle"] == 1
