"""SelfImprovementLoop が AutonomousScheduler から接続されていることのテスト。

orphaned だった self_improvement_loop を scheduler の _run_cycle 末尾に接続した
配線（設定 gate・例外隔離）を検証する。実 claude は呼ばない。
"""

from __future__ import annotations

import pytest

from core.scheduler import AutonomousScheduler


@pytest.fixture()
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    return tmp_path


async def test_self_improvement_disabled_by_default(isolated_home):
    sched = AutonomousScheduler(platform_home=isolated_home)
    result = await sched._maybe_run_self_improvement()
    assert result == {"enabled": False}


async def test_self_improvement_gated_on_config(isolated_home):
    sched = AutonomousScheduler(platform_home=isolated_home)
    sched._psm.save_platform_config({"daemon_self_improvement": True})

    # meta org が無い環境では ran=False（meta_org_not_found）になり、例外で落ちない
    result = await sched._maybe_run_self_improvement()
    assert result["enabled"] is True
    assert result["ran"] is False
    assert result["reason"] == "meta_org_not_found"


async def test_self_improvement_runs_loop_when_enabled(isolated_home, monkeypatch):
    sched = AutonomousScheduler(platform_home=isolated_home)
    sched._psm.save_platform_config({"daemon_self_improvement": True})

    class _Org:
        name = "Meta-Improvement Organization"

    monkeypatch.setattr(sched._psm, "load_organization_by_name", lambda name: _Org())
    monkeypatch.setattr(sched._psm, "get_org_state_manager", lambda org: object())

    ran = {"called": False}

    class _FakeLoop:
        def __init__(self, org, sm):
            pass

        async def run_improvement_cycle(self):
            ran["called"] = True

    monkeypatch.setattr("core.quality.self_improvement_loop.SelfImprovementLoop", _FakeLoop)

    result = await sched._maybe_run_self_improvement()
    assert result == {"enabled": True, "ran": True, "org": "Meta-Improvement Organization"}
    assert ran["called"] is True


async def test_self_improvement_failure_is_isolated(isolated_home, monkeypatch):
    sched = AutonomousScheduler(platform_home=isolated_home)
    sched._psm.save_platform_config({"daemon_self_improvement": True})

    class _Org:
        name = "Meta-Improvement Organization"

    monkeypatch.setattr(sched._psm, "load_organization_by_name", lambda name: _Org())
    monkeypatch.setattr(sched._psm, "get_org_state_manager", lambda org: object())

    class _BoomLoop:
        def __init__(self, org, sm):
            pass

        async def run_improvement_cycle(self):
            raise RuntimeError("boom")

    monkeypatch.setattr("core.quality.self_improvement_loop.SelfImprovementLoop", _BoomLoop)

    # 例外はメインサイクルを壊さず result に封じ込められる
    result = await sched._maybe_run_self_improvement()
    assert result["enabled"] is True
    assert result["ran"] is False
    assert "boom" in result["error"]
