"""
TeamCoordinator — チーム内エージェント連携 (A-11)
同一チームのエージェントが互いの作業結果を参照して協調する
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class CollaborationContext:
    task_id: str
    contributions: list[dict] = field(default_factory=list)


class TeamCoordinator:
    """タスク単位のコラボレーション文脈を保持する。"""

    def __init__(self):
        self._contexts: dict[str, CollaborationContext] = {}

    def create_context(self, task_id: str) -> CollaborationContext:
        if task_id not in self._contexts:
            self._contexts[task_id] = CollaborationContext(task_id=task_id)
        return self._contexts[task_id]

    def add_contribution(self, task_id: str, agent_id: str, output: str) -> None:
        context = self.create_context(task_id)
        context.contributions.append({
            "agent_id": agent_id,
            "output": output,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_context_for_agent(self, task_id: str, requesting_agent_id: str) -> str:
        context = self.create_context(task_id)
        others = [c for c in context.contributions if c.get("agent_id") != requesting_agent_id]
        if not others:
            return "チームメンバーの作業:\n(まだ他の貢献はありません)"

        lines = ["チームメンバーの作業:"]
        for contribution in others:
            output = str(contribution.get("output", ""))
            suffix = "..." if len(output) > 200 else ""
            lines.append(f"- {contribution.get('agent_id')}: {output[:200]}{suffix}")
        return "\n".join(lines)

    def synthesize_outputs(self, task_id: str) -> str:
        context = self.create_context(task_id)
        if not context.contributions:
            return "統合すべき出力がありません。"

        lines = [f"タスク {task_id} の統合サマリー:"]
        for contribution in context.contributions:
            lines.append(f"- {contribution['agent_id']}: {contribution['output']}")
        return "\n".join(lines)
