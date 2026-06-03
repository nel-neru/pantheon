"""
Core（中核エンジン）視点の賢いオーケストレーション

複数の Organization の中から「今どの Organization を改善すべきか」を
メトリクスに基づいて判断するロジック。

Sprint 1 アップグレード:
  - run_smart_improvement_cycle() 後に ScoreUpdater でスコア自動更新 (C-02)

Sprint N アップグレード:
  - PreTaskOrchestrator を統合。全タスクを実行前メタ分析経由に (N-06)
  - KnowledgeManager / OrchestrationPatternStore から最適実行計画を取得
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.metrics.balanced_growth import (
    calculate_group_metrics,
    calculate_organization_metrics,
    get_improvement_priority_score,
)
from core.metrics.score_updater import ExecutionOutcome, ScoreUpdater
from core.models.organization import GroupHQState, Organization, OrganizationMetrics
from core.quality.self_improvement_graph import run_improvement_for_organization
from core.state.manager import RepoStateManager


class GroupOrchestrator:
    """
    Core 視点で複数 Organization を賢く管理・改善するオーケストレーター

    Sprint N: 全タスクが PreTaskOrchestrator を経由して実行される。
    """

    def __init__(
        self,
        hq_state: GroupHQState,
        knowledge_manager: Optional[Any] = None,
        pattern_store: Optional[Any] = None,
        capability_registry: Optional[Any] = None,
    ):
        self.hq_state = hq_state
        self.state_managers: Dict[str, RepoStateManager] = {}
        self._score_updater = ScoreUpdater()

        # N-06: PreTaskOrchestrator を内部に持つ（全タスクはここを経由する）
        from core.orchestration.pre_task_orchestrator import PreTaskOrchestrator
        self._pre_task = PreTaskOrchestrator(
            capability_registry=capability_registry,
            knowledge_manager=knowledge_manager,
            pattern_store=pattern_store,
        )

    def register_state_manager(self, org_id: str, state_manager: RepoStateManager):
        self.state_managers[org_id] = state_manager

    def collect_organization_metrics(self) -> List[OrganizationMetrics]:
        """全Organizationのメトリクスを収集"""
        metrics_list = []
        for org in self.hq_state.organizations.values():
            pending = 0
            sm = self.state_managers.get(str(org.id))
            if sm:
                pending = len(sm.get_pending_improvement_proposals(limit=100))

            metrics = calculate_organization_metrics(
                organization=org,
                pending_proposals_count=pending,
            )
            metrics_list.append(metrics)
        return metrics_list

    def decide_next_organization_to_improve(
        self, metrics_list: List[OrganizationMetrics] | None = None
    ) -> tuple[Organization | None, float]:
        """
        今改善すべきOrganizationを決定
        Returns: (対象Organization, 優先度スコア)
        """
        if metrics_list is None:
            metrics_list = self.collect_organization_metrics()

        if not metrics_list:
            return None, 0.0

        # str(org.id) → UUID key のルックアップテーブルを O(N) で構築
        org_lookup: dict[str, object] = {
            str(org.id): key for key, org in self.hq_state.organizations.items()
        }

        scored = [
            (org_lookup[m.organization_id], get_improvement_priority_score(m))
            for m in metrics_list
            if m.organization_id in org_lookup
        ]

        if not scored:
            return None, 0.0

        best_org_key, best_score = max(scored, key=lambda x: x[1])
        target_org = self.hq_state.organizations.get(best_org_key)

        print(f"[GroupOrchestrator] 次に改善すべきOrganization: {target_org.name} (優先度スコア: {best_score})")
        return target_org, best_score

    async def run_smart_improvement_cycle(
        self,
        max_organizations: int = 3,
        max_cycles_per_org: int = 2,
    ):
        """
        賢くOrganizationを選んで改善サイクルを実行
        """
        print("\n=== Core 主導のスマート改善サイクル開始 ===\n")

        metrics_list = self.collect_organization_metrics()
        group_metrics = calculate_group_metrics(self.hq_state, metrics_list)

        print(f"グループ健康度: {group_metrics.group_health_score}")
        print(f"バランススコア: {group_metrics.balance_score}")
        print(f"最も弱いOrganization: {group_metrics.weakest_organization}")

        # 優先度の高い順に改善を実行
        sorted_metrics = sorted(
            metrics_list,
            key=get_improvement_priority_score,
            reverse=True,
        )

        # str(org.id) → Organization のルックアップテーブル
        org_by_str_id = {str(org.id): org for org in self.hq_state.organizations.values()}

        for i, metrics in enumerate(sorted_metrics[:max_organizations]):
            org = org_by_str_id.get(metrics.organization_id)
            if not org:
                continue

            sm = self.state_managers.get(str(org.id))
            if not sm:
                print(f"StateManagerが見つかりません: {org.name}")
                continue

            print(f"\n--- [{i+1}/{len(sorted_metrics)}] {org.name} の改善 ---")

            # N-06: PreTaskOrchestrator で実行計画を事前分析
            analysis = self._pre_task.analyze(
                "meta_improvement",
                f"{org.name} の改善サイクル",
            )
            print(
                f"    [PreTaskOrchestrator] パターン: {analysis.recommended_pattern} | "
                f"推奨エージェント: {analysis.recommended_agent_ids or '(デフォルト)'}"
            )

            result = await run_improvement_for_organization(
                org, sm, max_cycles=max_cycles_per_org
            )

            # C-02: 改善サイクル結果でスコアを自動更新
            outcome = self._build_outcome_from_cycle(result)
            self._score_updater.update(org, outcome, state_manager=sm)
            print(
                f"    → autonomy: {org.autonomy_score:.1f}  "
                f"velocity: {org.improvement_velocity:.1f}"
            )

        print("\n=== Core 主導のスマート改善サイクル終了 ===\n")

    def _build_outcome_from_cycle(self, cycle_result) -> ExecutionOutcome:
        """
        run_improvement_for_organization の戻り値から ExecutionOutcome を構築する。
        戻り値の型が不安定なため、安全に解析する。
        """
        if cycle_result is None:
            return ExecutionOutcome(success=False)
        try:
            # 辞書形式の場合
            if isinstance(cycle_result, dict):
                proposals = cycle_result.get("proposals", cycle_result.get("suggestions", []))
                accepted = sum(
                    1 for p in proposals
                    if isinstance(p, dict) and p.get("status") in ("approved", "accepted", "done")
                )
                return ExecutionOutcome(
                    success=True,
                    suggestions_count=len(proposals),
                    accepted_suggestions=accepted,
                    self_initiated=True,
                )
            # オブジェクトの場合（LangGraph state）
            proposals = getattr(cycle_result, "proposals", []) or []
            return ExecutionOutcome(
                success=True,
                suggestions_count=len(proposals),
                accepted_suggestions=0,
                self_initiated=True,
            )
        except Exception:
            return ExecutionOutcome(success=True, self_initiated=True)

    def get_group_status_summary(self) -> Dict:
        """現在のグループ状況のサマリーを返す（GUI用など）"""
        metrics_list = self.collect_organization_metrics()
        group_metrics = calculate_group_metrics(self.hq_state, metrics_list)

        return {
            "group_metrics": group_metrics,
            "organization_metrics": metrics_list,
            "total_organizations": len(self.hq_state.organizations),
        }
