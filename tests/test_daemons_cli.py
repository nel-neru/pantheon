"""Tests for the `pantheon daemons` CLI handlers (commands.daemons).

ここではプロセスを実起動しない: spawn_daemon を monkeypatch し、ハンドラが組み立てる
引数列だけを検証する。特に revenue は CLI フラグ（--target/--source-org/--min-reach）が
runner（core._revenue_daemon_runner）のパーサと 1:1 で噛み合うことを保証する。
"""

from __future__ import annotations

import argparse

import pytest

import commands.daemons as daemons
import core.runtime.daemon_registry as registry
from core._revenue_daemon_runner import build_parser


def _start_ns(**over):
    ns = argparse.Namespace(
        name="revenue",
        interval=None,
        max_files=10,
        target=0.0,
        source_org="HQ",
        min_reach=0.0,
    )
    for k, v in over.items():
        setattr(ns, k, v)
    return ns


@pytest.fixture
def captured_spawn(monkeypatch):
    calls: list[dict] = []

    def fake_spawn(name, *, args=(), **_kw):
        calls.append({"name": name, "args": list(args)})
        return {"status": "started", "pid": 123, "log_path": "revenue.log"}

    monkeypatch.setattr(registry, "spawn_daemon", fake_spawn)
    return calls


async def test_start_revenue_passes_target_source_org_and_min_reach(captured_spawn):
    await daemons.cmd_daemons_start(
        _start_ns(target=50000.0, source_org="動画制作社", min_reach=1000.0)
    )

    assert len(captured_spawn) == 1
    extra = captured_spawn[0]["args"]
    assert captured_spawn[0]["name"] == "revenue"
    assert "--target=50000.0" in extra
    assert "--source-org-name=動画制作社" in extra
    assert "--min-reach=1000.0" in extra


async def test_start_revenue_extra_args_parse_back_into_runner(captured_spawn):
    """CLI が組み立てた引数列を runner のパーサがそのまま受理し、正しい値になる
    （フラグ名のドリフトを捕まえる drift guard）。"""
    await daemons.cmd_daemons_start(
        _start_ns(target=42000.0, source_org="アフィリ社", min_reach=250.0)
    )
    extra = captured_spawn[0]["args"]

    parsed = build_parser().parse_args(extra)
    assert parsed.target == 42000.0
    assert parsed.source_org_name == "アフィリ社"
    assert parsed.min_reach == 250.0
    assert parsed.interval == 24 * 3600  # interval 未指定 → revenue の既定が入る


async def test_start_revenue_defaults_are_safe(captured_spawn):
    """フラグ未指定なら安全な既定（target=0=アイドル, source=HQ, min_reach=0=フィルタ無し）。"""
    await daemons.cmd_daemons_start(_start_ns())
    parsed = build_parser().parse_args(captured_spawn[0]["args"])
    assert parsed.target == 0.0
    assert parsed.source_org_name == "HQ"
    assert parsed.min_reach == 0.0


async def test_start_non_revenue_omits_revenue_flags(captured_spawn):
    """revenue 以外には revenue 専用フラグを付けない（他 daemon の runner を壊さない）。"""
    await daemons.cmd_daemons_start(_start_ns(name="trend"))
    extra = captured_spawn[0]["args"]
    assert captured_spawn[0]["name"] == "trend"
    assert not any(a.startswith("--source-org-name") for a in extra)
    assert not any(a.startswith("--min-reach") for a in extra)
    assert not any(a.startswith("--target") for a in extra)


async def test_execute_approved_default_off_not_forwarded(captured_spawn):
    """既定オフ: --execute-approved は付かず、runner も execute_approved=False（HITL 据え置き）。"""
    await daemons.cmd_daemons_start(_start_ns(target=1000.0))
    extra = captured_spawn[0]["args"]
    assert "--execute-approved" not in extra
    assert build_parser().parse_args(extra).execute_approved is False


async def test_execute_approved_flag_forwards_and_parses_back(captured_spawn):
    """opt-in: --execute-approved が CLI→runner へ 1:1 で渡り、parse で True になる（drift guard）。"""
    await daemons.cmd_daemons_start(_start_ns(target=1000.0, execute_approved=True))
    extra = captured_spawn[0]["args"]
    assert "--execute-approved" in extra
    assert build_parser().parse_args(extra).execute_approved is True
