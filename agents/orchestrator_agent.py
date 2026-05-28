"""
OrchestratorAgent — CLI からのすべてのタスクの中央ルーター

設計思想:
  CLI は常にこのエージェントにだけ依頼する。
  OrchestratorAgent が PreTaskOrchestrator を通じてタスクを分析し、
  AgentFactory で最適エージェントを選択・実行する。

  CLI → OrchestratorAgent.run(task)
           ↓  PreTaskOrchestrator.analyze()   — タスク種別・複雑度・最適パターンを判断
           ↓  AgentFactory.create(agent_id)   — 最適エージェントを動的生成
           ↓  agent.run(task)                 — 実際の作業を実行
           ↑  AgentResult                     — 結果を CLI に返す
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from agents.base import AgentResult, AgentTask, BaseAgent
from core.models.organization import AgentSkill, SpecialistAgent

logger = logging.getLogger(__name__)


class OrchestratorAgent(BaseAgent):
    """
    RepoCorp AI の中央オーケストレーターエージェント。

    このエージェントは自身でタスクを実行するのではなく、
    PreTaskOrchestrator の分析結果に基づき最適な専門エージェントを
    選択・実行する「指揮者」として機能する。

    Usage:
        agent = OrchestratorAgent.create()
        result = await agent.run(AgentTask(task_type="code_review", description="..."))
    """

    def __init__(
        self,
        specialist: Optional[SpecialistAgent] = None,
        llm_client: Optional[Any] = None,
        **_kwargs: Any,
    ):
        if specialist is None:
            specialist = SpecialistAgent(
                name="Orchestrator",
                skills=[
                    AgentSkill.AGENT_WORKFLOW_DESIGN,
                    AgentSkill.STRATEGIC_PLANNING,
                ],
            )
        super().__init__(specialist)
        self._llm_client = llm_client
        self._orchestrator = None  # 遅延初期化

    @classmethod
    def create(
        cls,
        llm_client: Optional[Any] = None,
        **_kwargs: Any,
    ) -> "OrchestratorAgent":
        """デフォルト設定でOrchestratorAgentを生成する。"""
        return cls(llm_client=llm_client)

    def _get_orchestrator(self):
        """PreTaskOrchestrator の遅延取得。"""
        if self._orchestrator is None:
            from core.orchestration.orchestration_pattern_store import OrchestrationPatternStore
            from core.orchestration.pre_task_orchestrator import PreTaskOrchestrator

            store = OrchestrationPatternStore()
            self._orchestrator = PreTaskOrchestrator(
                llm_client=self._llm_client,
                pattern_store=store,
            )
        return self._orchestrator

    async def run(self, task: AgentTask) -> AgentResult:
        """
        タスクを受け取り、最適なエージェントにルーティングして実行する。

        Flow:
          1. PreTaskOrchestrator.analyze() でタスクを分析
          2. 推奨パターン（単一/逐次/並列/レビューループ）と推奨エージェントIDを取得
          3. PreTaskOrchestrator.execute() で実際に実行
          4. 結果を返す
        """
        orchestrator = self._get_orchestrator()

        logger.info(
            "OrchestratorAgent: analyzing task_type=%s", task.task_type
        )

        analysis = orchestrator.analyze(task.task_type, task.description)

        logger.info(
            "OrchestratorAgent: pattern=%s agents=%s",
            analysis.recommended_pattern,
            analysis.recommended_agent_ids,
        )

        try:
            result = await orchestrator.execute(task, analysis)

            if not isinstance(result, AgentResult):
                return AgentResult(
                    success=True,
                    output={
                        "analysis_only": True,
                        "recommended_pattern": analysis.recommended_pattern,
                        "recommended_agents": analysis.recommended_agent_ids,
                        "reasoning": analysis.reasoning,
                    },
                    thinking_process="No agent factory — returned analysis only",
                )

            return result

        except Exception as exc:  # noqa: BLE001
            logger.error("OrchestratorAgent: execution failed: %s", exc, exc_info=True)
            return AgentResult(
                success=False,
                error=str(exc),
                thinking_process=f"pattern={analysis.recommended_pattern}, agents={analysis.recommended_agent_ids}",
            )

    def describe_routing(self, task_type: str, description: str) -> Dict[str, Any]:
        """
        実行せずにルーティング計画だけを返すデバッグ用メソッド。
        `repocorp orchestration analyze` コマンドで使用。
        """
        orchestrator = self._get_orchestrator()
        analysis = orchestrator.analyze(task_type, description)
        routing = {
            "task_type": task_type,
            "recommended_pattern": analysis.recommended_pattern,
            "recommended_agents": analysis.recommended_agent_ids,
            "complexity": analysis.complexity,
            "spawn_new_agent": analysis.spawn_new_agent,
            "reasoning": analysis.research_notes,
        }
        return routing
