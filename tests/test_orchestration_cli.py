"""
Tests for N-07/N-10 orchestration CLI commands.
Patches core.platform.state.get_platform_home to use tmp_path.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch


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
            OrchestrationPatternStore,
            PatternRecord,
        )
        from main import cmd_orchestration_history

        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            store = OrchestrationPatternStore()
            store.record(
                PatternRecord(
                    task_type="code_review",
                    pattern="review_loop",
                    agent_ids=["R1"],
                    success=True,
                    quality_score=8.0,
                )
            )
            store.record(
                PatternRecord(
                    task_type="code_review",
                    pattern="review_loop",
                    agent_ids=["R1"],
                    success=False,
                    quality_score=4.0,
                )
            )
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

    # ── --resolve: 検出ギャップを CapabilityGapResolver で解消する本番ドライバ ──
    @staticmethod
    def _agent_gap():
        from core.intelligence.capability_gap_analyzer import CapabilityGap

        return CapabilityGap(
            gap_id="gap:deep_research",
            pattern_key="p",
            description="research が必要",
            suggested_type="agent",
            suggested_name="deep_research",
            rationale="needed",
            priority="high",
        )

    @staticmethod
    def _team_gap():
        from core.intelligence.capability_gap_analyzer import CapabilityGap

        return CapabilityGap(
            gap_id="gap:security_team",
            pattern_key="p",
            description="security team が必要",
            suggested_type="team",
            suggested_name="Security",
            rationale="needed",
            priority="high",
        )

    def test_resolve_spawns_agent_for_gap(self, capsys, tmp_path):
        """--resolve は org をロードし、agent ギャップを実際に spawn してサマリーを出す。"""
        from core.models.organization import Organization
        from main import cmd_orchestration_capabilities

        org = Organization(name="TestOrg", purpose="p")
        with (
            patch("core.platform.state.get_platform_home", return_value=tmp_path),
            patch(
                "core.intelligence.capability_gap_analyzer.CapabilityGapAnalyzer.get_all_gaps",
                return_value=[self._agent_gap()],
            ),
            patch(
                "core.platform.state.PlatformStateManager.load_organizations",
                return_value=[org],
            ),
        ):
            _run(cmd_orchestration_capabilities(SimpleNamespace(resolve=True, org_name=None)))
        out = capsys.readouterr().out
        assert "能力ギャップ解消結果" in out
        assert "対象 org: TestOrg" in out
        assert "spawned agents : 1" in out

    def test_resolve_no_org_skips_gracefully(self, capsys, tmp_path):
        """org が未登録なら --resolve はクラッシュせず WARN を出してスキップする。"""
        from main import cmd_orchestration_capabilities

        with (
            patch("core.platform.state.get_platform_home", return_value=tmp_path),
            patch(
                "core.intelligence.capability_gap_analyzer.CapabilityGapAnalyzer.get_all_gaps",
                return_value=[self._agent_gap()],
            ),
        ):
            _run(cmd_orchestration_capabilities(SimpleNamespace(resolve=True, org_name=None)))
        out = capsys.readouterr().out
        assert "Organization が未登録" in out
        assert "能力ギャップ解消結果" not in out

    def test_resolve_org_not_found_warns(self, capsys, tmp_path):
        """--org-name が見つからなければ WARN を出してスキップする。"""
        from main import cmd_orchestration_capabilities

        with (
            patch("core.platform.state.get_platform_home", return_value=tmp_path),
            patch(
                "core.intelligence.capability_gap_analyzer.CapabilityGapAnalyzer.get_all_gaps",
                return_value=[self._agent_gap()],
            ),
        ):
            _run(
                cmd_orchestration_capabilities(SimpleNamespace(resolve=True, org_name="NoSuchOrg"))
            )
        out = capsys.readouterr().out
        assert "見つかりません" in out
        assert "能力ギャップ解消結果" not in out

    def test_no_resolve_flag_leaves_resolution_off(self, capsys, tmp_path):
        """--resolve 不在なら org・gap があっても解消ブロックを一切出さない（既定オフ）。"""
        from core.models.organization import Organization
        from main import cmd_orchestration_capabilities

        org = Organization(name="TestOrg", purpose="p")
        with (
            patch("core.platform.state.get_platform_home", return_value=tmp_path),
            patch(
                "core.intelligence.capability_gap_analyzer.CapabilityGapAnalyzer.get_all_gaps",
                return_value=[self._agent_gap()],
            ),
            patch(
                "core.platform.state.PlatformStateManager.load_organizations",
                return_value=[org],
            ),
        ):
            _run(cmd_orchestration_capabilities(SimpleNamespace()))
        out = capsys.readouterr().out
        assert "能力ギャップ解消結果" not in out
        assert "検出された能力ギャップ" in out  # 表示自体は従来どおり行う

    def test_resolve_persists_org_only_on_structure_auto_apply(self, capsys, tmp_path):
        """構造ギャップが auto-apply された時だけ org を save する（spawn では save しない）。

        既定の HITL 経路では構造は提案止まりで org は不変なので save 不要。spawn は registry
        側で永続するため org save 対象外。両ケースで save 呼び出しの有無を検証する。
        """
        from core.models.organization import Organization
        from main import cmd_orchestration_capabilities

        org = Organization(name="TestOrg", purpose="p")
        spawn_summary = {
            "spawned_agents": 1,
            "proposed_teams": 0,
            "proposed_divisions": 0,
            "auto_applied": 1,
            "results": [{"action": "spawned_agent", "detail": "spawned: X", "auto_applied": True}],
        }
        structure_summary = {
            "spawned_agents": 0,
            "proposed_teams": 1,
            "proposed_divisions": 0,
            "auto_applied": 1,
            "results": [{"action": "proposed_team", "detail": "applied", "auto_applied": True}],
        }
        for summary, expect_saved in ((spawn_summary, False), (structure_summary, True)):
            with (
                patch("core.platform.state.get_platform_home", return_value=tmp_path),
                patch(
                    "core.intelligence.capability_gap_analyzer.CapabilityGapAnalyzer.get_all_gaps",
                    return_value=[self._agent_gap()],
                ),
                patch(
                    "core.platform.state.PlatformStateManager.load_organizations",
                    return_value=[org],
                ),
                patch(
                    "core.orchestration.capability_gap_loop.resolve_gaps_for_org",
                    return_value=summary,
                ),
                patch("core.platform.state.PlatformStateManager.save_organization") as mock_save,
            ):
                _run(cmd_orchestration_capabilities(SimpleNamespace(resolve=True, org_name=None)))
            assert mock_save.called is expect_saved

    def test_resolve_persists_structure_proposal_to_inbox(self, capsys, tmp_path):
        """team/division 構造ギャップは org の state manager に提案として永続化され、
        /inbox（API `_pending_proposals_for` と同じ get_pending_improvement_proposals）
        から取得できる＝承認ハブと接続する（C15: 検出→PolicyEngine→永続化→GUI の閉ループ）。

        既定 HITL（policy.yaml 無し）では auto-apply されず status='pending'（active）で
        残ることを実コードで検証する（resolver は mock しない＝真の永続経路を通す）。
        """
        from core.models.organization import Organization
        from core.platform.state import PlatformStateManager
        from main import cmd_orchestration_capabilities

        org = Organization(name="TestOrg", purpose="p")
        with (
            patch("core.platform.state.get_platform_home", return_value=tmp_path),
            patch(
                "core.intelligence.capability_gap_analyzer.CapabilityGapAnalyzer.get_all_gaps",
                return_value=[self._team_gap()],
            ),
            patch(
                "core.platform.state.PlatformStateManager.load_organizations",
                return_value=[org],
            ),
        ):
            _run(cmd_orchestration_capabilities(SimpleNamespace(resolve=True, org_name=None)))
            # API/Inbox が読むのと同一経路で永続化提案を取得できることを確認する。
            sm = PlatformStateManager().get_org_state_manager(org)
            pending = sm.get_pending_improvement_proposals(limit=10)

        assert len(pending) == 1, "構造提案が /inbox 経路に永続化されていない（ループ未閉鎖）"
        proposal = pending[0]
        assert proposal["category"] == "org_structure"
        assert proposal["status"] == "pending"  # 既定 HITL＝auto-apply されない
        assert "Team" in proposal["title"]
        # サマリーにも提案 1 件・auto-applied 0 と正直に出る
        out = capsys.readouterr().out
        assert "proposed teams : 1" in out
        assert "auto-applied   : 0" in out

    def test_resolve_structure_proposal_is_idempotent_on_rerun(self, capsys, tmp_path):
        """同一ギャップで --resolve を 2 回実行しても、構造提案は 1 件に保たれる
        （id を gap_id から決定論的に導出＝再生成で上書き）。重複が /inbox に積み上がらない。"""
        from core.models.organization import Organization
        from core.platform.state import PlatformStateManager
        from main import cmd_orchestration_capabilities

        org = Organization(name="TestOrg", purpose="p")
        with (
            patch("core.platform.state.get_platform_home", return_value=tmp_path),
            patch(
                "core.intelligence.capability_gap_analyzer.CapabilityGapAnalyzer.get_all_gaps",
                return_value=[self._team_gap()],
            ),
            patch(
                "core.platform.state.PlatformStateManager.load_organizations",
                return_value=[org],
            ),
        ):
            _run(cmd_orchestration_capabilities(SimpleNamespace(resolve=True, org_name=None)))
            _run(cmd_orchestration_capabilities(SimpleNamespace(resolve=True, org_name=None)))
            sm = PlatformStateManager().get_org_state_manager(org)
            pending = sm.get_pending_improvement_proposals(limit=10)

        assert len(pending) == 1, "再 --resolve で構造提案が重複している（id 非決定論）"

    def test_resolve_does_not_persist_for_agent_only_gap(self, capsys, tmp_path):
        """agent/skill ギャップは registry へ spawn されるだけで、org の improvements
        には提案が書かれない（構造提案だけが /inbox に出る＝面の正直さ）。"""
        from core.models.organization import Organization
        from core.platform.state import PlatformStateManager
        from main import cmd_orchestration_capabilities

        org = Organization(name="TestOrg", purpose="p")
        with (
            patch("core.platform.state.get_platform_home", return_value=tmp_path),
            patch(
                "core.intelligence.capability_gap_analyzer.CapabilityGapAnalyzer.get_all_gaps",
                return_value=[self._agent_gap()],
            ),
            patch(
                "core.platform.state.PlatformStateManager.load_organizations",
                return_value=[org],
            ),
        ):
            _run(cmd_orchestration_capabilities(SimpleNamespace(resolve=True, org_name=None)))
            sm = PlatformStateManager().get_org_state_manager(org)
            pending = sm.get_pending_improvement_proposals(limit=10)

        # spawn ブランチが実際に走った上で（no-op ではなく）提案が書かれないことを確認
        assert "spawned agents : 1" in capsys.readouterr().out
        assert pending == []


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
            OrchestrationPatternStore,
            PatternRecord,
        )
        from main import cmd_orchestration_self_review

        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            store = OrchestrationPatternStore()
            for i in range(5):
                store.record(
                    PatternRecord(
                        task_type="code_review",
                        pattern="single_agent",
                        agent_ids=["A1"],
                        success=(i == 0),
                        quality_score=3.0,
                    )
                )
            _run(cmd_orchestration_self_review(SimpleNamespace()))

        out = capsys.readouterr().out
        assert "改善が必要" in out or "失敗率" in out

    def test_self_review_no_issues_all_succeed(self, capsys, tmp_path):
        from core.orchestration.orchestration_pattern_store import (
            OrchestrationPatternStore,
            PatternRecord,
        )
        from main import cmd_orchestration_self_review

        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            store = OrchestrationPatternStore()
            for _ in range(5):
                store.record(
                    PatternRecord(
                        task_type="code_review",
                        pattern="review_loop",
                        agent_ids=["R1"],
                        success=True,
                        quality_score=9.0,
                    )
                )
            _run(cmd_orchestration_self_review(SimpleNamespace()))

        assert (
            "問題のあるオーケストレーションパターンは見つかりませんでした"
            in capsys.readouterr().out
        )
