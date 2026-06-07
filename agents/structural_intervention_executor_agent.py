"""
Structural Intervention Executor Agent

承認済みの cross-org 構造介入提案を、対象 Organization のモデルに安全に適用する
SpecialistAgent。ImprovementExecutorAgent（コードファイル適用）の兄弟であり、
ファイルではなく Organization / Division / Team / SpecialistAgent を変更する。

ImprovementExecutorAgent と違い LLM 生成は行わない（介入仕様を決定論的に適用する）。
すべての適用は PreTaskOrchestrator 経由でこの agent に到達し、適用前に呼び出し側で
PolicyEngine の承認を必ず通している前提（no-bypass 不変条件）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.models.organization import SpecialistAgent

from .base import AgentResult, AgentTask, BaseAgent


class StructuralInterventionExecutorAgent(BaseAgent):
    """承認済み構造介入を対象 Organization に適用する SpecialistAgent。"""

    def __init__(self, specialist: SpecialistAgent, provider_name: str = "claude_code"):
        super().__init__(specialist)
        self._provider_name = provider_name

    async def run(self, task: AgentTask) -> AgentResult:
        from core.orchestration.structural_intervention import (
            StructuralInterventionError,
            apply_structural_intervention,
        )
        from core.platform.state import PlatformStateManager

        proposal = task.input.get("proposal")
        if not proposal:
            return AgentResult(success=False, error="task.input.proposal がありません。")

        platform_home: Optional[str] = task.input.get("platform_home")
        psm = PlatformStateManager(platform_home=Path(platform_home) if platform_home else None)

        try:
            summary = apply_structural_intervention(proposal, psm=psm)
        except StructuralInterventionError as exc:
            return AgentResult(success=False, error=str(exc))

        if not summary.get("applied"):
            # 冪等スキップ（既に存在等）。失敗ではないが変更なしであることを伝える。
            return AgentResult(
                success=True,
                output=summary,
                thinking_process="構造介入は既に適用済み（冪等スキップ）。",
                execution_log=str(summary.get("reason") or "no change"),
            )

        title = self._summarize(summary)
        return AgentResult(
            success=True,
            output=summary,
            thinking_process=f"構造介入を適用: {title}",
            execution_log=f"{summary.get('organization_name')}: {title}",
        )

    @staticmethod
    def _summarize(summary: dict) -> str:
        itype = summary.get("intervention_type", "intervention")
        if "added_division" in summary:
            return f"{itype} → Division '{summary['added_division']}' を追加"
        if "added_team" in summary:
            return f"{itype} → Team '{summary['added_team']}' を追加"
        if "added_agent" in summary:
            return f"{itype} → Agent '{summary['added_agent']}' を追加"
        if "skills_added" in summary:
            return f"{itype} → スキル {summary['skills_added']} を注入"
        if "goal" in summary:
            return f"{itype} → 目標 '{summary['goal']}' を設定"
        return itype
