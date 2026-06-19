"""
Meta-Improvement Organization が改善提案を自動で拾って対応するフロー

自己成長ループの核心部分。Organization 内の Agent を使って実際に改善を実行する。
"""

from __future__ import annotations

from typing import List

from core.models.organization import Organization
from core.state.manager import RepoStateManager


class SelfImprovementLoop:
    """
    Meta-Improvement Organization が主導する自己改善ループ
    """

    def __init__(
        self,
        organization: Organization,
        state_manager: RepoStateManager,
        *,
        orchestrator=None,
        agent_factory=None,
    ):
        self.organization = organization
        self.state_manager = state_manager
        # テスト/呼び出し側が注入可能（省略時は実行時に配線）。__init__ は 2-positional を維持。
        self._orchestrator = orchestrator
        self._agent_factory = agent_factory

    def _resolve_orchestrator(self):
        if self._orchestrator is not None and self._agent_factory is not None:
            return self._orchestrator, self._agent_factory
        from core.quality.improvement_orchestration import build_improvement_orchestrator

        orchestrator, factory = build_improvement_orchestrator()
        self._orchestrator = self._orchestrator or orchestrator
        self._agent_factory = self._agent_factory or factory
        return self._orchestrator, self._agent_factory

    @staticmethod
    def _quality_from_result(result) -> float:
        """実行結果から品質スコア(0-10)を導出する。

        既定は成功/失敗ベースのヒューリスティック。result.output に review_score /
        quality_score があればそれを優先（将来の厳格レビュー連携に備える）。
        """
        output = getattr(result, "output", None)
        if isinstance(output, dict):
            for key in ("quality_score", "review_score", "overall_score"):
                value = output.get(key)
                if isinstance(value, (int, float)):
                    return float(value)
        return 8.0 if getattr(result, "success", False) else 2.0

    async def pickup_and_prioritize_proposals(self) -> List[dict]:
        """
        .pantheon/improvements/ から未対応の提案を拾い、優先度付けする
        """
        raw_proposals = self.state_manager.get_pending_improvement_proposals(limit=30)

        prioritized = sorted(
            raw_proposals,
            # 生 JSON 由来の提案は expected_impact が null のことがある（legacy/手編集/外部生成）。
            # ``.get(k, "")`` は **キーが null 値で存在すると "" でなく None を返す** ため、
            # ソート比較で ``None < str`` の TypeError がこの load-bearing ループ全体を落とす
            # （scheduler の try/except に飲まれ、自己改善が静かに永久停止する）。``or ""`` で coerce。
            key=lambda p: (p.get("priority") == "high", p.get("expected_impact") or ""),
            reverse=True,
        )

        print(f"[SelfImprovementLoop] 未対応提案を {len(prioritized)} 件取得・優先度付け完了")
        return prioritized

    async def assign_and_execute_improvements(self, proposals: List[dict]):
        """
        優先度の高い改善提案を PreTaskOrchestrator 経由で実行する。

        従来の ``ImprovementExecutorAgent(agents[0])`` ハードコードを廃止し、
        Pre-Task メタ分析 → CapabilityRegistry/TaskRouter のスキルマッチで最適
        エージェントを選定。実行結果（品質スコア・所要時間）は
        OrchestrationPatternStore / CapabilityRegistry にフィードバックされる。
        """
        from agents.base import AgentTask

        orchestrator, factory = self._resolve_orchestrator()

        for prop in proposals[:5]:
            title = prop.get("title", "")
            print(f"[SelfImprovementLoop] 提案を処理中: {title} (優先度: {prop.get('priority')})")

            file_path = prop.get("file_path", "")
            if not file_path:
                print(f"  → file_path なしのため実行不可（meta-level 提案）: {title}")
                continue

            description = f"改善提案の適用: {title}"
            task = AgentTask(
                task_type="improvement_execution",
                description=description,
                input={
                    "repo_path": str(self.state_manager.repo_path),
                    "suggestion": prop,
                },
            )
            try:
                analysis = orchestrator.analyze(
                    "improvement_execution", description, context={"description": description}
                )
                if not analysis.recommended_agent_ids:
                    # ルーティングが空でも改善実行担当へフォールバック
                    analysis.recommended_agent_ids = ["agent:improvement_executor"]

                # record=False で実行 → 実 quality と timing を付けて 1 回だけ記録
                result = await orchestrator.execute(
                    task, analysis, agent_factory=factory.create, record=False
                )
                quality = self._quality_from_result(result)
                orchestrator._record_execution(
                    task,
                    analysis,
                    result,
                    quality_score=quality,
                    execution_time_ms=getattr(orchestrator, "_last_execution_ms", 0),
                )

                if getattr(result, "success", False):
                    print(f"  → 適用完了: {getattr(result, 'output', '')}")
                    self.state_manager.update_proposal_status(str(prop.get("id", "")), "done")
                else:
                    print(f"  → 適用失敗: {getattr(result, 'error', '')}")
                    self.state_manager.update_proposal_status(str(prop.get("id", "")), "failed")
            except Exception as e:
                print(f"  → エラー: {e}")
                self.state_manager.update_proposal_status(str(prop.get("id", "")), "failed")

    async def run_improvement_cycle(self):
        """
        一回の自己改善サイクルを実行するエントリーポイント
        """
        print(f"\n=== {self.organization.name} 自己改善サイクル開始 ===")
        proposals = await self.pickup_and_prioritize_proposals()
        if not proposals:
            print("[SelfImprovementLoop] 未対応の改善提案はありませんでした。")
            return

        await self.assign_and_execute_improvements(proposals)
        print("=== 自己改善サイクル終了 ===\n")
