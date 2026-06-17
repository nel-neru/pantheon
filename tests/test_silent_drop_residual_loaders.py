"""Cycle 24 — silent-drop 観測性の残ローダーへの横展開。

agent_knowledge / capability_history / org_snapshot の各ローダーは破損レコードを
``except: continue`` / ``return {}`` で黙殺しており、学習パターン・能力追加履歴・
組織スナップショットの母数が静かに目減りしていた。``warn_skipped_state_file`` 経由で
観測可能にしつつ、スキップして処理継続する挙動（ファイルは温存）は保つ。
"""

from __future__ import annotations

import json
import logging

from core.hierarchy.org_snapshot import OrgSnapshotManager
from core.intelligence.agent_knowledge import AgentKnowledgeAccumulator
from core.intelligence.capability_history import CapabilityHistoryTracker

_STATE_LOGGER = "core.platform.state"


def _valid_pattern(task_type: str = "analysis") -> dict:
    return {
        "pattern_id": "p1",
        "agent_id": "a1",
        "skill_name": "deep_research",
        "task_type": task_type,
        "pattern_summary": "ok",
        "success_score": 9.0,
        "created_at": "2026-06-18T00:00:00+00:00",
    }


def test_agent_knowledge_warns_on_malformed_line(tmp_path, caplog):
    """壊れた 1 行はスキップしつつ、学習パターンの母数目減りを警告で観測可能にする。"""
    acc = AgentKnowledgeAccumulator(platform_home=tmp_path)
    acc.pattern_file.write_text(
        json.dumps(_valid_pattern("analysis")) + "\n{ broken json\n",
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger=_STATE_LOGGER):
        patterns = acc.get_patterns_for_task("analysis")

    assert [p.pattern_id for p in patterns] == ["p1"]
    assert any("SuccessPattern" in rec.message for rec in caplog.records)
    assert acc.pattern_file.exists()  # 黙殺と違い温存（修復すれば次回読める）


def test_capability_history_warns_on_malformed_line(tmp_path, caplog):
    """壊れた 1 行はスキップしつつ、能力追加履歴の母数目減りを観測可能にする。"""
    tracker = CapabilityHistoryTracker(platform_home=tmp_path)
    valid = {
        "capability_id": "c1",
        "capability_name": "NewSkill",
        "capability_type": "skill",
        "reason": "gap",
        "gap_description": "missing",
        "added_at": "2026-06-18T00:00:00+00:00",
    }
    tracker.file_path.write_text(
        json.dumps(valid) + "\n{ broken\n",
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger=_STATE_LOGGER):
        history = tracker.get_history()

    assert [c.capability_id for c in history] == ["c1"]
    assert any("CapabilityAddition" in rec.message for rec in caplog.records)
    assert tracker.file_path.exists()


def test_org_snapshot_list_warns_on_corrupt_snapshot(tmp_path, caplog):
    """破損スナップショットはスキップしつつ、一覧の目減りを観測可能にする。"""
    mgr = OrgSnapshotManager(platform_home=tmp_path)
    valid = {
        "snapshot_id": "TestOrg_001",
        "org_name": "TestOrg",
        "org_data": {"name": "TestOrg"},
        "created_at": "2026-06-18T00:00:00+00:00",
        "label": "",
    }
    (mgr.snapshots_dir / "TestOrg_001.json").write_text(json.dumps(valid), encoding="utf-8")
    (mgr.snapshots_dir / "TestOrg_bad.json").write_text("{ broken json", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger=_STATE_LOGGER):
        snapshots = mgr.list_snapshots("TestOrg")

    assert [s.snapshot_id for s in snapshots] == ["TestOrg_001"]
    assert any("OrgSnapshot" in rec.message for rec in caplog.records)


def test_org_snapshot_restore_warns_on_corrupt_file(tmp_path, caplog):
    """破損スナップショットの復元失敗は黙って {} を返さず観測可能にする。"""
    mgr = OrgSnapshotManager(platform_home=tmp_path)
    (mgr.snapshots_dir / "TestOrg_900.json").write_text("{ broken json", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger=_STATE_LOGGER):
        result = mgr.restore_snapshot("TestOrg_900")

    assert result == {}
    assert any("OrgSnapshot" in rec.message for rec in caplog.records)
