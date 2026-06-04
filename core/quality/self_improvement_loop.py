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

    def __init__(self, organization: Organization, state_manager: RepoStateManager):
        self.organization = organization
        self.state_manager = state_manager

    async def pickup_and_prioritize_proposals(self) -> List[dict]:
        """
        .pantheon/improvements/ から未対応の提案を拾い、優先度付けする
        """
        raw_proposals = self.state_manager.get_pending_improvement_proposals(limit=30)

        prioritized = sorted(
            raw_proposals,
            key=lambda p: (p.get("priority") == "high", p.get("expected_impact", "")),
            reverse=True,
        )

        print(f"[SelfImprovementLoop] 未対応提案を {len(prioritized)} 件取得・優先度付け完了")
        return prioritized

    async def assign_and_execute_improvements(self, proposals: List[dict]):
        """
        優先度の高い改善提案を Agent に割り当てて実行する
        """
        from agents.base import AgentTask
        from agents.improvement_executor_agent import ImprovementExecutorAgent

        agents = self.organization.get_all_agents()
        if not agents:
            print("[SelfImprovementLoop] エージェントが存在しません。改善をスキップします。")
            return

        executor_agent = ImprovementExecutorAgent(agents[0])

        for prop in proposals[:5]:
            title = prop.get("title", "")
            print(f"[SelfImprovementLoop] 提案を処理中: {title} (優先度: {prop.get('priority')})")

            file_path = prop.get("file_path", "")
            if not file_path:
                print(f"  → file_path なしのため実行不可（meta-level 提案）: {title}")
                continue

            task = AgentTask(
                task_type="improvement_execution",
                description=f"改善提案の適用: {title}",
                input={
                    "repo_path": str(self.state_manager.repo_path),
                    "suggestion": prop,
                },
            )
            try:
                result = await executor_agent.run(task)
                if result.success:
                    print(f"  → 適用完了: {result.output}")
                    self.state_manager.update_proposal_status(str(prop.get("id", "")), "done")
                else:
                    print(f"  → 適用失敗: {result.error}")
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
