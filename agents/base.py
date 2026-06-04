"""
Pantheon - Agent Execution Base

全 SpecialistAgent の実行インターフェース定義。

アップグレード (Sprint 1):
  - _enrich_with_knowledge(): 実行前にKnowledgeManagerから知見を注入 (B-01)
  - _save_execution_knowledge(): 実行後に学習知識を保存 (B-02)
  - _apply_skills_to_prompt(): スキルをシステムプロンプトに反映 (A-01)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from core.models.organization import AgentSkill, SpecialistAgent

if TYPE_CHECKING:
    from core.knowledge.manager import KnowledgeManager


logger = logging.getLogger(__name__)


@dataclass
class AgentTask:
    """エージェントへの入力タスク"""
    task_type: str
    description: str
    input: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """エージェントの実行結果"""
    success: bool
    output: Dict[str, Any] = field(default_factory=dict)
    thinking_process: str = ""
    execution_log: str = ""
    error: Optional[str] = None


class BaseAgent(ABC):
    """全 SpecialistAgent の基底クラス"""

    def __init__(self, specialist: SpecialistAgent):
        self.specialist = specialist
        self._skill_engine: Optional[Any] = None  # AgentSkillEngine (遅延初期化)
        self.knowledge_manager: Optional[Any] = None

    @abstractmethod
    async def run(self, task: AgentTask) -> AgentResult:
        """タスクを実行して結果を返す"""

    async def safe_run(self, task: AgentTask) -> AgentResult:
        """標準化されたエラーハンドリング付きでタスクを実行する。"""
        try:
            return await self.run(task)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Agent %s failed while executing task %s",
                self.name,
                task.task_type,
            )
            return self.handle_run_error(task, exc)

    def handle_run_error(self, task: AgentTask, error: Exception) -> AgentResult:
        """safe_run() で利用する標準エラー結果を返す。"""
        return AgentResult(
            success=False,
            output={
                "agent_name": self.name,
                "task_type": task.task_type,
                "task_description": task.description,
            },
            thinking_process="エージェント実行中に内部エラーが発生しました。",
            execution_log=f"{type(error).__name__}: {error}",
            error=str(error),
        )

    @property
    def name(self) -> str:
        return self.specialist.name

    @property
    def skills(self) -> List[AgentSkill]:
        return list(self.specialist.skills)

    def __repr__(self) -> str:
        skills = [s.value for s in self.specialist.skills]
        return f"{self.__class__.__name__}(name={self.name!r}, skills={skills})"

    # ------------------------------------------------------------------ #
    # スキルエンジン統合 (A-01~A-03)                                       #
    # ------------------------------------------------------------------ #

    def _get_skill_engine(self):
        """AgentSkillEngine の遅延取得（循環インポート回避）。"""
        if self._skill_engine is None:
            from core.intelligence.agent_skill_engine import AgentSkillEngine
            self._skill_engine = AgentSkillEngine()
        return self._skill_engine

    def apply_skills_to_prompt(self, base_prompt: str) -> str:
        """
        エージェントのスキルをシステムプロンプトに注入する。
        サブクラスは SYSTEM_PROMPT を apply_skills_to_prompt() で
        ラップすることでスキルを有効化できる。
        """
        return self._get_skill_engine().apply_skills_to_prompt(
            base_prompt, self.specialist.skills
        )

    def get_skill_tags(self) -> List[str]:
        """このエージェントのスキルに対応するナレッジタグを返す。"""
        return self._get_skill_engine().get_skill_tags(self.specialist.skills)

    # ------------------------------------------------------------------ #
    # 知識ループ統合 (B-01~B-02)                                           #
    # ------------------------------------------------------------------ #

    def _enrich_with_knowledge(
        self,
        knowledge_manager: Optional["KnowledgeManager"] = None,
        extra_tags: Optional[List[str]] = None,
        limit: int = 5,
    ) -> str:
        """
        実行前にナレッジマネージャーから関連知識を取得して返す。
        返却文字列をプロンプトに追加することで過去の学習を活用できる。

        Args:
            knowledge_manager: KnowledgeManager インスタンス
            extra_tags: スキルタグに追加するタグ
            limit: 取得する知識の最大件数

        Returns:
            プロンプトに埋め込める形式の知識文字列（ない場合は空文字）
        """
        manager = knowledge_manager or self.knowledge_manager
        if manager is None:
            return ""

        tags = self.get_skill_tags()
        if extra_tags:
            tags = tags + extra_tags
        return manager.get_context_for_agent(tags=tags, limit=limit)

    def _save_execution_knowledge(
        self,
        knowledge_manager: "KnowledgeManager",
        result: AgentResult,
        task: AgentTask,
        extra_tags: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        実行結果から学習知識を生成してナレッジマネージャーに保存する。
        成功した実行のみ保存し、失敗は _save_failure_knowledge() で別途管理する。

        Returns:
            保存された insight_id（保存しなかった場合は None）
        """
        if not result.success:
            return None

        manager = knowledge_manager or self.knowledge_manager
        if manager is None:
            return None

        tags = self.get_skill_tags()
        if extra_tags:
            tags = tags + extra_tags

        content = (
            f"タスク: {task.description}\n"
            f"エージェント: {self.name} (スキル: {', '.join(self.get_skill_tags())})\n"
            f"結果サマリー: {result.thinking_process}\n"
            f"実行ログ: {result.execution_log}"
        )

        return manager.save_insight(
            title=f"[{self.name}] {task.task_type}: {task.description[:60]}",
            content=content,
            tags=tags,
            source_org=self.name,
            importance="medium",
        )
