"""
Asset Executor Agent

承認済みの content_asset 提案を、対象 Organization の target_repo ワークスペース *内部に*
安全に書き込む SpecialistAgent（Phase 6/7）。ImprovementExecutorAgent（既存コードファイルの
LLM 書換）とは別で、新規/更新のコンテンツ資産（記事・コピー・スクリプト）を扱う。

外部投稿・公開は行わない（ワークスペース内アーティファクト生成までに限定）。すべての適用は
PolicyEngine 承認後・PreTaskOrchestrator 経由でこの agent に到達する。
"""

from __future__ import annotations

from pathlib import Path

from core.models.organization import SpecialistAgent

from .base import AgentResult, AgentTask, BaseAgent


class AssetExecutorAgent(BaseAgent):
    """承認済み content_asset をワークスペース内に安全適用する SpecialistAgent。"""

    def __init__(self, specialist: SpecialistAgent, provider_name: str = "claude_code"):
        super().__init__(specialist)
        self._provider_name = provider_name

    async def run(self, task: AgentTask) -> AgentResult:
        from core.orchestration.asset_application import (
            AssetApplicationError,
            apply_content_asset,
        )

        proposal = task.input.get("proposal")
        if not proposal:
            return AgentResult(success=False, error="task.input.proposal がありません。")

        repo_path = task.input.get("repo_path")
        if not repo_path:
            return AgentResult(
                success=False, error="task.input.repo_path（ワークスペース）が必要です。"
            )

        try:
            summary = apply_content_asset(proposal, repo_root=Path(repo_path))
        except (AssetApplicationError, OSError) as exc:
            # OSError も拾う（万一の IsADirectoryError/PermissionError 等を未捕捉例外にしない）
            return AgentResult(success=False, error=str(exc))

        if not summary.get("applied"):
            return AgentResult(
                success=True,
                output=summary,
                thinking_process="資産は既に存在（冪等スキップ）。",
                execution_log=str(summary.get("reason") or "no change"),
            )

        return AgentResult(
            success=True,
            output=summary,
            thinking_process=f"資産を {summary.get('mode')} で適用: {summary.get('file_path')}",
            execution_log=f"{summary.get('file_path')} ({summary.get('bytes_written')} bytes)",
        )
