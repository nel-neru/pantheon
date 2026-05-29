"""
Tests for N-07/N-10 orchestration CLI commands.
Patches core.platform.state.get_platform_home to use tmp_path.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


# ═══════════════════════════════════════════════════════════════
# cmd_orchestration_analyze (N-07)
# ═══════════════════════════════════════════════════════════════

class TestOrchestrationAnalyzeCLI:
    def test_analyze_code_review(self, capsys, tmp_path):
        """code_review タスクの実行計画が出力される"""
        from main import cmd_orchestration_analyze
        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            _run(cmd_orchestration_analyze(SimpleNamespace(task_type="code_review")))
        out = capsys.readouterr().out
        assert "code_review" in out
        assert "推奨パターン" in out
        assert "複雑度" in out

    def test_analyze_meta_improvement_hierarchical(self, capsys, tmp_path):
        """meta_improvement → hierarchical パターンを推奨する"""
        from main import cmd_orchestration_analyze
        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            _run(cmd_orchestration_analyze(SimpleNamespace(task_type="meta_improvement")))
        assert "hierarchical" in capsys.readouterr().out

    def test_analyze_unknown_task_falls_back_to_default(self, capsys, tmp_path):
        """未知タスクでもデフォルトで出力する"""
        from main import cmd_orchestration_analyze
        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            _run(cmd_orchestration_analyze(SimpleNamespace(task_type="unknown_xyz_task")))
        assert "unknown_xyz_task" in capsys.readouterr().out

    def test_analyze_security_audit(self, capsys, tmp_path):
        """security_audit → review_loop パターン"""
        from main import cmd_orchestration_analyze
        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            _run(cmd_orchestration_analyze(SimpleNamespace(task_type="security_audit")))
        assert "review_loop" in capsys.readouterr().out


# ═══════════════════════════════════════════════════════════════
# cmd_orchestration_history (N-07)
# ═══════════════════════════════════════════════════════════════

class TestOrchestrationHistoryCLI:
    def test_history_empty(self, capsys, tmp_path):
        """履歴なしで適切なガイドメッセージ"""
        from main import cmd_orchestration_history
        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            _run(cmd_orchestration_history(SimpleNamespace()))
        assert "実行履歴がまだありません" in capsys.readouterr().out

    def test_history_with_records(self, capsys, tmp_path):
        """レコードあり → タスク種別と統計が表示される"""
        from core.orchestration.orchestration_pattern_store import (
            OrchestrationPatternStore, PatternRecord,
        )
        from main import cmd_orchestration_history

        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            store = OrchestrationPatternStore()
            store.record(PatternRecord(
                task_type="code_review", pattern="review_loop",
                agent_ids=["R1"], success=True, quality_score=8.0,
            ))
            store.record(PatternRecord(
                task_type="code_review", pattern="review_loop",
                agent_ids=["R1"], success=False, quality_score=4.0,
            ))
            _run(cmd_orchestration_history(SimpleNamespace()))

        out = capsys.readouterr().out
        assert "code_review" in out


# ═══════════════════════════════════════════════════════════════
# cmd_orchestration_capabilities (N-07)
# ═══════════════════════════════════════════════════════════════

class TestOrchestrationCapabilitiesCLI:
    def test_empty_registry_shows_header(self, capsys, tmp_path):
        from main import cmd_orchestration_capabilities
        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            _run(cmd_orchestration_capabilities(SimpleNamespace()))
        assert "Capability Registry" in capsys.readouterr().out

    def test_no_gaps_shows_ok(self, capsys, tmp_path):
        from main import cmd_orchestration_capabilities
        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            _run(cmd_orchestration_capabilities(SimpleNamespace()))
        assert "ギャップなし" in capsys.readouterr().out


# ═══════════════════════════════════════════════════════════════
# cmd_orchestration_self_review (N-10)
# ═══════════════════════════════════════════════════════════════

class TestOrchestratorSelfReview:
    def test_self_review_empty(self, capsys, tmp_path):
        from main import cmd_orchestration_self_review
        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            _run(cmd_orchestration_self_review(SimpleNamespace()))
        assert "十分な実行履歴がありません" in capsys.readouterr().out

    def test_self_review_detects_high_failure_rate(self, capsys, tmp_path):
        from core.orchestration.orchestration_pattern_store import (
            OrchestrationPatternStore, PatternRecord,
        )
        from main import cmd_orchestration_self_review

        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            store = OrchestrationPatternStore()
            for i in range(5):
                store.record(PatternRecord(
                    task_type="code_review", pattern="single_agent",
                    agent_ids=["A1"], success=(i == 0), quality_score=3.0,
                ))
            _run(cmd_orchestration_self_review(SimpleNamespace()))

        out = capsys.readouterr().out
        assert "改善が必要" in out or "失敗率" in out

    def test_self_review_no_issues_all_succeed(self, capsys, tmp_path):
        from core.orchestration.orchestration_pattern_store import (
            OrchestrationPatternStore, PatternRecord,
        )
        from main import cmd_orchestration_self_review

        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            store = OrchestrationPatternStore()
            for _ in range(5):
                store.record(PatternRecord(
                    task_type="code_review", pattern="review_loop",
                    agent_ids=["R1"], success=True, quality_score=9.0,
                ))
            _run(cmd_orchestration_self_review(SimpleNamespace()))

        assert "問題のあるオーケストレーションパターンは見つかりませんでした" in capsys.readouterr().out
