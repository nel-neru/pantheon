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

    def test_resolve_marks_satisfied_gap_implemented(self, capsys, tmp_path):
        """--resolve で実 spawn された agent ギャップは capability_gaps.json で implemented になり、
        active ビュー（get_all_gaps）から畳まれる。さもないと解消後も同じギャップが残り、次回
        --resolve で再 spawn され format_for_agent/get_summary が「不足」と over-report し続ける。"""
        from core.intelligence.capability_gap_analyzer import CapabilityGapAnalyzer
        from core.models.organization import Organization
        from main import cmd_orchestration_capabilities

        org = Organization(name="TestOrg", purpose="p")
        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            # 能力が無かった頃に検出された永続ギャップを再現（実ファイルに書く＝get_all_gaps が読む）。
            seed = CapabilityGapAnalyzer(platform_home=tmp_path)
            seed._gaps.append(self._agent_gap())
            seed._save_gaps()
            # 前提: 解消前は active として読める。
            assert any(
                g.gap_id == "gap:deep_research"
                for g in CapabilityGapAnalyzer(platform_home=tmp_path).get_all_gaps()
            )
            with patch(
                "core.platform.state.PlatformStateManager.load_organizations",
                return_value=[org],
            ):
                _run(cmd_orchestration_capabilities(SimpleNamespace(resolve=True, org_name=None)))

        out = capsys.readouterr().out
        assert "spawned agents : 1" in out
        assert "marked done    : 1" in out  # 充足ギャップが1件 implemented にマークされた

        # 永続化を確認: active ビューから消え、include_implemented で implemented=True で残る。
        reloaded = CapabilityGapAnalyzer(platform_home=tmp_path)
        assert not any(g.gap_id == "gap:deep_research" for g in reloaded.get_all_gaps())
        all_gaps = reloaded.get_all_gaps(include_implemented=True)
        marked = [g for g in all_gaps if g.gap_id == "gap:deep_research"]
        assert marked and marked[0].implemented is True

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


# ═══════════════════════════════════════════════════════════════
# cmd_orchestration_capabilities --unused（非推奨候補レポート）
# ═══════════════════════════════════════════════════════════════


class TestOrchestrationCapabilitiesUnusedCLI:
    @staticmethod
    def _seed(tmp_path, *, added_days_ago: float, name: str = "DustyAgent"):
        """指定日数前に追加された未使用能力を registry へ永続化する。"""
        from datetime import datetime, timedelta, timezone

        from core.intelligence.capability_registry import CapabilityEntry, CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register(
            CapabilityEntry(
                id=name.lower(),
                name=name,
                capability_type="agent",
                added_at=(datetime.now(timezone.utc) - timedelta(days=added_days_ago)).isoformat(),
                usage_count=0,
                last_used=None,
            )
        )

    def test_unused_flag_lists_stale_capability(self, capsys, tmp_path):
        """--unused は閾値より古い未使用能力を非推奨候補セクションに一覧する。"""
        from main import cmd_orchestration_capabilities

        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            self._seed(tmp_path, added_days_ago=200)
            _run(cmd_orchestration_capabilities(SimpleNamespace(unused=90)))
        out = capsys.readouterr().out
        # 「Agents」一覧にも名前は出るので、非推奨候補ヘッダ以降のセクションで検証する。
        section = out.split("非推奨候補")[1]
        assert " 1 件" in section
        assert "DustyAgent" in section

    def test_unused_flag_excludes_recent_capability(self, capsys, tmp_path):
        """追加が新しい未使用能力は閾値内なので非推奨候補に出さない（C27 セマンティクス）。"""
        from main import cmd_orchestration_capabilities

        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            self._seed(tmp_path, added_days_ago=5, name="FreshAgent")
            _run(cmd_orchestration_capabilities(SimpleNamespace(unused=90)))
        out = capsys.readouterr().out
        assert "非推奨候補（最終アクティビティから 90 日以上） 0 件" in out
        # FreshAgent は Agents 一覧には出るが、非推奨候補セクションには出ない。
        section = out.split("非推奨候補")[1]
        assert "FreshAgent" not in section

    def test_without_flag_no_unused_section(self, capsys, tmp_path):
        """フラグ無し（既定）では非推奨候補セクションを出さない＝従来挙動を保つ。"""
        from main import cmd_orchestration_capabilities

        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            self._seed(tmp_path, added_days_ago=200)
            _run(cmd_orchestration_capabilities(SimpleNamespace()))
        out = capsys.readouterr().out
        assert "非推奨候補" not in out

    def test_unused_custom_threshold(self, capsys, tmp_path):
        """--unused 10 のように閾値を指定でき、ヘッダにも反映される。"""
        from main import cmd_orchestration_capabilities

        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            self._seed(tmp_path, added_days_ago=30)
            _run(cmd_orchestration_capabilities(SimpleNamespace(unused=10)))
        out = capsys.readouterr().out
        assert "最終アクティビティから 10 日以上" in out
        assert "DustyAgent" in out.split("非推奨候補")[1]

    def test_unused_report_shows_id_for_deprecate(self, capsys, tmp_path):
        """--unused レポートは id を併記し、そのまま --deprecate に渡せる。"""
        from main import cmd_orchestration_capabilities

        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            self._seed(tmp_path, added_days_ago=200)
            _run(cmd_orchestration_capabilities(SimpleNamespace(unused=90)))
        section = capsys.readouterr().out.split("非推奨候補")[1]
        assert "[id: dustyagent]" in section


# ═══════════════════════════════════════════════════════════════
# cmd_orchestration_capabilities --deprecate（非推奨化 HITL アクション）
# ═══════════════════════════════════════════════════════════════


class TestOrchestrationCapabilitiesDeprecateCLI:
    @staticmethod
    def _seed(tmp_path, *, cap_id: str = "dustyagent", name: str = "DustyAgent"):
        from datetime import datetime, timedelta, timezone

        from core.intelligence.capability_registry import CapabilityEntry, CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register(
            CapabilityEntry(
                id=cap_id,
                name=name,
                capability_type="agent",
                added_at=(datetime.now(timezone.utc) - timedelta(days=200)).isoformat(),
                usage_count=0,
                last_used=None,
            )
        )

    def test_deprecate_by_id_persists_and_excludes_from_unused(self, capsys, tmp_path):
        """--deprecate <id> で is_active=False を永続化し、以後 --unused 候補から消える。"""
        from core.intelligence.capability_registry import CapabilityRegistry
        from main import cmd_orchestration_capabilities

        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            self._seed(tmp_path)
            _run(cmd_orchestration_capabilities(SimpleNamespace(deprecate="dustyagent")))
            out = capsys.readouterr().out
            # 永続状態を実ファイルから読み直して非推奨が残ることを確認（出力文言任せにしない）。
            reloaded = CapabilityRegistry()
            assert reloaded.get("dustyagent").is_active is False
            # 非推奨後の --unused レポートに当該 id が出ない。
            _run(cmd_orchestration_capabilities(SimpleNamespace(unused=90)))
            section = capsys.readouterr().out.split("非推奨候補")[1]

        assert "非推奨にしました" in out
        assert "dustyagent" not in section

    def test_deprecate_by_name_resolves_to_entry(self, capsys, tmp_path):
        """--deprecate <表示名> も find_by_name で解決して非推奨化できる。"""
        from core.intelligence.capability_registry import CapabilityRegistry
        from main import cmd_orchestration_capabilities

        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            self._seed(tmp_path)
            _run(cmd_orchestration_capabilities(SimpleNamespace(deprecate="DustyAgent")))
            reloaded = CapabilityRegistry()
            active = reloaded.get("dustyagent").is_active

        assert active is False
        assert "非推奨にしました" in capsys.readouterr().out

    def test_deprecate_unknown_warns_and_no_change(self, capsys, tmp_path):
        """存在しない能力を --deprecate しても WARN を出すだけでクラッシュしない。"""
        from core.intelligence.capability_registry import CapabilityRegistry
        from main import cmd_orchestration_capabilities

        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            self._seed(tmp_path)
            _run(cmd_orchestration_capabilities(SimpleNamespace(deprecate="no-such-cap")))
            reloaded = CapabilityRegistry()
            active = reloaded.get("dustyagent").is_active

        out = capsys.readouterr().out
        assert "見つかりません" in out
        assert active is True  # 無関係な能力は不変

    def test_without_deprecate_flag_no_action(self, capsys, tmp_path):
        """--deprecate 不在（既定）では非推奨化ブロックを一切出さない＝従来挙動。"""
        from main import cmd_orchestration_capabilities

        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            self._seed(tmp_path)
            _run(cmd_orchestration_capabilities(SimpleNamespace()))
        out = capsys.readouterr().out
        assert "非推奨にしました" not in out
