"""
フロー堅牢化の回帰テスト。

Atlas 解析で検出した高重要度バグの修正を固定する:
  - orchestration: batch_execute の asyncio NameError
  - chat: run_chat() の PROVIDER_LABEL_MAP NameError
  - profile: ActivityTracker のタイムゾーン非対応 datetime
  - state: CLI org remove がシステム Organization を削除できる
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace

import pytest

import commands.org as org_cmd


def test_pre_task_orchestrator_batch_execute_has_asyncio():
    import core.orchestration.pre_task_orchestrator as pto

    assert pto.asyncio.__name__ == "asyncio"
    orchestrator = pto.PreTaskOrchestrator()
    results = asyncio.run(
        orchestrator.batch_execute([{"task_type": "default", "context": {"description": "demo"}}])
    )
    assert isinstance(results, list)
    assert results and results[0]["success"] is True


def test_chat_provider_label_map_defined():
    from agents import chat_agent

    assert isinstance(chat_agent.PROVIDER_LABEL_MAP, dict)
    # 既知の provider はラベル化、未知の値はそのまま返る
    assert chat_agent.PROVIDER_LABEL_MAP.get("anthropic")
    assert chat_agent.PROVIDER_LABEL_MAP.get("mystery", "mystery") == "mystery"


def test_activity_tracker_timestamp_is_timezone_aware(tmp_path):
    from core.profile.activity_tracker import ActivityTracker

    tracker = ActivityTracker(platform_home=tmp_path)
    tracker.record_activity("pantheon atlas")
    line = (tmp_path / "activity_log.jsonl").read_text(encoding="utf-8").strip().splitlines()[0]
    record = json.loads(line)
    parsed = datetime.fromisoformat(record["timestamp"])
    assert parsed.tzinfo is not None, "activity timestamp must be timezone-aware"


def _fake_psm(org, removed):
    return SimpleNamespace(
        load_organization_by_name=lambda name: org,
        remove_organization=lambda org_id: removed.append(org_id),
    )


def test_org_remove_blocks_system_org_without_force():
    removed: list[str] = []
    system_org = SimpleNamespace(id="sys-1", name="Meta-Improvement Organization", is_system=True)
    args = SimpleNamespace(name="Meta-Improvement Organization", yes=True, force=False)

    with pytest.raises(SystemExit):
        asyncio.run(
            org_cmd.cmd_org_remove(
                args,
                confirm_action=lambda *a, **k: True,
                get_psm=lambda: _fake_psm(system_org, removed),
            )
        )
    assert removed == [], "system Organization must NOT be removed without --force"


def test_org_remove_allows_system_org_with_force():
    removed: list[str] = []
    system_org = SimpleNamespace(id="sys-1", name="Meta-Improvement Organization", is_system=True)
    args = SimpleNamespace(name="Meta-Improvement Organization", yes=True, force=True)

    asyncio.run(
        org_cmd.cmd_org_remove(
            args,
            confirm_action=lambda *a, **k: True,
            get_psm=lambda: _fake_psm(system_org, removed),
        )
    )
    assert removed == ["sys-1"]


def test_org_remove_allows_normal_org():
    removed: list[str] = []
    normal_org = SimpleNamespace(id="org-9", name="MyApp", is_system=False)
    args = SimpleNamespace(name="MyApp", yes=True, force=False)

    asyncio.run(
        org_cmd.cmd_org_remove(
            args,
            confirm_action=lambda *a, **k: True,
            get_psm=lambda: _fake_psm(normal_org, removed),
        )
    )
    assert removed == ["org-9"]
