"""
PreTaskOrchestrator — 全タスク実行前メタ分析・最適エージェント選択 (Theme N)

==========================================================================
設計哲学（2025年AIマルチエージェントオーケストレーション最新知見に基づく）
==========================================================================

従来の問題：
  タスクが発生すると即座に固定エージェントが実行する。
  「このタスクを誰がどうやってやるべきか」を考えない。

解決する原則：
  ALL execution must go through Pre-Task Meta-Analysis first:

  1. ANALYZE — タスク種別・複雑度・要件を分析
  2. RESEARCH — CapabilityRegistry + KnowledgeManager から最良アプローチを調査
  3. SELECT/SPAWN — 最適エージェントを選択、なければ動的作成
  4. EXECUTE — 選択されたオーケストレーションパターンで実行
  5. LEARN — 結果からパターンをナレッジとして保存

これを実装することで、システムは常に「最善の方法で仕事をする」ことを
自律的に判断できるようになる。

参考アーキテクチャ：
  - LangGraph: Router Node パターン
  - CrewAI: Manager Agent による動的割り当て
  - AutoGen: Meta-Agent によるエージェント選択
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Pre-Task ルーティングの再入ガード。execute() 実行中は True になり、
# 内部で呼ばれるエージェントが再び route を起動して無限再帰するのを防ぐ。
_ROUTING_ACTIVE: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "pretask_routing_active", default=False
)


def is_routing_active() -> bool:
    """現在 Pre-Task ルーティング（execute）の内側かどうか。"""
    return _ROUTING_ACTIVE.get()


# ────────────────────────────────────────────────────────────────────────── #
# オーケストレーションパターン定義                                             #
# ────────────────────────────────────────────────────────────────────────── #


class OrchestrationPattern:
    """
    利用可能なオーケストレーションパターン。

    ベストプラクティス調査結果に基づき、タスク特性ごとに
    最適なパターンを選択する。
    """

    SINGLE_AGENT = "single_agent"
    """単一専門エージェント。シンプルで明確なタスクに最適。"""

    SEQUENTIAL_PIPELINE = "sequential_pipeline"
    """エージェントA → エージェントB の順次実行。前工程の出力が次工程の入力。"""

    PARALLEL_THEN_MERGE = "parallel_then_merge"
    """複数エージェントが並列実行 → 結果を統合。独立サブタスクに最適。"""

    REVIEW_LOOP = "review_loop"
    """実行エージェント + レビューエージェントのループ。品質重視タスクに最適。"""

    HIERARCHICAL = "hierarchical"
    """マネージャーエージェントが複数ワーカーを指揮。複雑な長期タスクに最適。"""

    BEST_OF_N = "best_of_n"
    """複数エージェントが独立実行 → 最良結果を採用。高精度が必要なタスクに最適。"""


@dataclass
class TaskAnalysis:
    """Pre-Task 分析結果。このオブジェクトが実行計画の全て。"""

    task_type: str
    description: str
    complexity: str = "medium"  # "low" | "medium" | "high"
    recommended_pattern: str = OrchestrationPattern.SINGLE_AGENT
    recommended_agent_ids: List[str] = field(default_factory=list)
    spawn_new_agent: bool = False  # 既存エージェントが不適切な場合
    spawn_spec: Optional[Dict] = None  # 新エージェントの仕様
    research_notes: str = ""  # ベストプラクティス調査メモ
    estimated_tokens: int = 0
    confidence: float = 0.8  # 0.0〜1.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_type": self.task_type,
            "description": self.description,
            "complexity": self.complexity,
            "recommended_pattern": self.recommended_pattern,
            "recommended_agent_ids": self.recommended_agent_ids,
            "spawn_new_agent": self.spawn_new_agent,
            "spawn_spec": self.spawn_spec,
            "research_notes": self.research_notes,
            "estimated_tokens": self.estimated_tokens,
            "confidence": self.confidence,
            "created_at": self.created_at,
        }


# ────────────────────────────────────────────────────────────────────────── #
# タスク種別 → オーケストレーション特性マッピング                              #
# ────────────────────────────────────────────────────────────────────────── #

TASK_ORCHESTRATION_PROFILES = {
    "code_review": {
        "complexity": "medium",
        "pattern": OrchestrationPattern.REVIEW_LOOP,
        "required_skills": ["codebase_exploration", "performance_analysis", "tool_integration"],
        "min_agents": 1,
        "notes": "コードレビューはまずコードベース調査エージェントで構造を把握し、"
        "次にCodeReviewAgentで詳細レビュー、最後にInternalConsultantでレビューするのが最善。",
    },
    "improvement_execution": {
        "complexity": "high",
        "pattern": OrchestrationPattern.SEQUENTIAL_PIPELINE,
        "required_skills": ["prompt_engineering", "tool_integration"],
        "min_agents": 1,
        "notes": "コード変更は: 1)現状把握 → 2)変更生成 → 3)テスト確認 の順が安全。",
    },
    "codebase_exploration": {
        "complexity": "low",
        "pattern": OrchestrationPattern.SINGLE_AGENT,
        "required_skills": ["codebase_exploration", "deep_research"],
        "min_agents": 1,
        "notes": "コードベース調査は CodebaseExplorerAgent が最も効率的（キャッシュ活用）。",
    },
    "meta_improvement": {
        "complexity": "high",
        "pattern": OrchestrationPattern.HIERARCHICAL,
        "required_skills": ["strategic_planning", "agent_workflow_design"],
        "min_agents": 2,
        "notes": "システム自己改善は: 1)メトリクス収集 → 2)優先度判定 → 3)改善生成 → 4)Human承認 が必須。",
    },
    "security_audit": {
        "complexity": "high",
        "pattern": OrchestrationPattern.REVIEW_LOOP,
        "required_skills": ["tool_integration", "deep_research"],
        "min_agents": 1,
        "notes": "セキュリティ監査は専門スキルを持つエージェントを優先し、"
        "InternalConsultantによる二重チェックを必ず行う。",
    },
    "knowledge_curation": {
        "complexity": "low",
        "pattern": OrchestrationPattern.SINGLE_AGENT,
        "required_skills": ["knowledge_curation"],
        "min_agents": 1,
        "notes": "知識整理は単一エージェントで十分。ただし知識ループを活用すること。",
    },
    "organization_design": {
        "complexity": "high",
        "pattern": OrchestrationPattern.SEQUENTIAL_PIPELINE,
        "required_skills": ["org_design", "strategic_planning"],
        "min_agents": 2,
        "notes": "組織設計は: 1)現状分析 → 2)設計案生成 → 3)戦略的検証 の順序が重要。",
    },
    "structural_intervention": {
        "complexity": "medium",
        "pattern": OrchestrationPattern.SINGLE_AGENT,
        "required_skills": ["org_design", "agent_workflow_design"],
        "min_agents": 1,
        "notes": "HQ→子 Organization の構造介入は、承認済み仕様を決定論的に適用する単一エージェントで安全。",
    },
    "default": {
        "complexity": "medium",
        "pattern": OrchestrationPattern.SINGLE_AGENT,
        "required_skills": [],
        "min_agents": 1,
        "notes": "汎用タスク。単一エージェントで開始し、必要に応じて拡張する。",
    },
}


# ────────────────────────────────────────────────────────────────────────── #
# PreTaskOrchestrator                                                          #
# ────────────────────────────────────────────────────────────────────────── #


class PreTaskOrchestrator:
    """
    全タスク実行前のメタ分析・最適エージェント選択エンジン。

    使い方:
        orchestrator = PreTaskOrchestrator(
            capability_registry=registry,
            knowledge_manager=knowledge,
            pattern_detector=detector,
        )
        analysis = orchestrator.analyze("code_review", "セキュリティ脆弱性の検出", ...)
        # → analysis.recommended_pattern, analysis.recommended_agent_ids が決まる
        result = await orchestrator.execute(task, analysis)
    """

    def __init__(
        self,
        capability_registry=None,
        knowledge_manager=None,
        pattern_detector=None,
        pattern_store=None,  # OrchestrationPatternStore
        llm_client=None,
        agent_factory=None,  # AgentFactory インスタンス（省略時は自動生成）
    ):
        self._registry = capability_registry
        self._knowledge = knowledge_manager
        self._detector = pattern_detector
        self._pattern_store = pattern_store
        self._llm = llm_client
        self._execution_log: List[Dict] = []
        self._exec_started_at: float | None = None  # execute() の計時開始（monotonic）
        self._last_execution_ms: int = 0  # 直近 execute() の所要ミリ秒
        # TaskRouter を内部で使う（CapabilityRegistry と共有）
        from core.orchestration.task_router import TaskRouter

        self._task_router = TaskRouter(capability_registry=capability_registry)
        # BestPracticeAdvisor を内部で使う
        from core.orchestration.best_practice_advisor import BestPracticeAdvisor

        self._advisor = BestPracticeAdvisor(
            knowledge_manager=knowledge_manager,
            pattern_store=pattern_store,
        )
        # AgentFactory — 省略時はデフォルトを自動生成
        if agent_factory is not None:
            self._agent_factory = agent_factory
        else:
            try:
                from agents.agent_factory import AgentFactory

                self._agent_factory = AgentFactory(llm_client=llm_client)
            except Exception:
                self._agent_factory = None

    # ──────────────────────────────────────────────────────────── #
    # Step 1: ANALYZE                                               #
    # ──────────────────────────────────────────────────────────── #

    def analyze(
        self,
        task_type: str,
        description: str,
        context: Optional[Dict] = None,
    ) -> TaskAnalysis:
        """
        タスクを分析して最適な実行計画を返す。

        1. タスクプロファイルからデフォルト計画を取得
        2. 過去の実行パターンから学習された改善を適用
        3. CapabilityRegistry から最適エージェントを選択
        """
        profile = TASK_ORCHESTRATION_PROFILES.get(task_type, TASK_ORCHESTRATION_PROFILES["default"])

        # Step 2: ナレッジから過去のベストプラクティスを取得
        research_notes = self._research_best_practice(task_type, description)

        # Step 3: TaskRouter でエージェントを選択（CapabilityRegistry ベース）
        routing = self._task_router.route(task_type, max_agents=profile.get("min_agents", 1) + 1)
        recommended_ids = routing.selected_agent_ids

        # Step 3b: パターンストアから学習された最良パターンで上書き
        if self._pattern_store:
            learned_pattern = self._pattern_store.get_best_pattern(task_type)
            if learned_pattern:
                profile = {**profile, "pattern": learned_pattern}

        # Step 4: 既存エージェントが要件を満たさない場合のスポーン判定
        spawn_new = routing.fallback_used and not recommended_ids
        spawn_spec = self._build_spawn_spec(profile["required_skills"]) if spawn_new else None

        analysis = TaskAnalysis(
            task_type=task_type,
            description=description,
            complexity=profile["complexity"],
            recommended_pattern=profile["pattern"],
            recommended_agent_ids=recommended_ids,
            spawn_new_agent=spawn_new,
            spawn_spec=spawn_spec,
            research_notes=research_notes or profile["notes"],
            estimated_tokens=self._estimate_tokens(task_type, profile["complexity"]),
            confidence=0.9 if recommended_ids else 0.5,
        )

        logger.info(
            "PreTaskOrchestrator.analyze: %s → pattern=%s agents=%s",
            task_type,
            analysis.recommended_pattern,
            analysis.recommended_agent_ids,
        )
        return analysis

    async def batch_execute(self, tasks: list[dict], max_parallel: int = 3) -> list[dict]:
        """Analyze independent tasks in parallel batches."""
        semaphore = asyncio.Semaphore(max_parallel)

        async def worker(task_def: dict) -> dict:
            async with semaphore:
                task_type = task_def.get("task_type", "default")
                context = task_def.get("context", {}) or {}
                description = context.get("description", task_type)
                try:
                    analysis = self.analyze(task_type, description, context=context)
                    return {
                        "task_type": task_type,
                        "success": True,
                        "recommended_pattern": analysis.recommended_pattern,
                        "recommended_agent_ids": analysis.recommended_agent_ids,
                        "analysis": analysis.to_dict(),
                    }
                except Exception as exc:
                    return {
                        "task_type": task_type,
                        "success": False,
                        "error": str(exc),
                    }

        return await asyncio.gather(*(worker(task_def) for task_def in tasks))

    # ──────────────────────────────────────────────────────────── #
    # Step 2: RESEARCH                                              #
    # ──────────────────────────────────────────────────────────── #

    def _research_best_practice(self, task_type: str, description: str) -> str:
        """
        BestPracticeAdvisor を使って過去の実行知識とパターン統計を取得する。
        """
        return self._advisor.advise(task_type, description)

    # ──────────────────────────────────────────────────────────── #
    # Step 3: SELECT / SPAWN                                        #
    # ──────────────────────────────────────────────────────────── #

    def _select_agents(self, required_skills: List[str], min_agents: int = 1) -> List[str]:
        """
        CapabilityRegistry からスキル要件に合うエージェントを選択する。
        スキルマッチ率の高い順にソートして返す。
        """
        if not self._registry:
            return []

        agents = self._registry.list_agents()
        if not agents:
            return []

        if not required_skills:
            # スキル要件なし → 全エージェントから先頭を返す
            return [a.id for a in agents[:min_agents]]

        # スキルマッチスコアでランキング
        scored = []
        for agent in agents:
            agent_skills = set(agent.skills)
            required_set = set(required_skills)
            match_count = len(agent_skills & required_set)
            if match_count > 0 or not required_skills:
                scored.append((agent.id, match_count))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [aid for aid, _ in scored[: max(min_agents, 2)]]

    def _build_spawn_spec(self, required_skills: List[str]) -> Dict:
        """
        既存エージェントが不足している場合の新エージェント仕様を生成する。
        DynamicAgentSpawner が実際の作成に使う。
        """
        return {
            "skills": required_skills[:3],  # max 3 skills per SpecialistAgent
            "reason": f"タスク要件 ({', '.join(required_skills)}) に合うエージェントが存在しない",
        }

    def _estimate_tokens(self, task_type: str, complexity: str) -> int:
        """タスク種別と複雑度からトークン使用量を概算する。"""
        base = {"low": 1000, "medium": 4000, "high": 8000}.get(complexity, 4000)
        multipliers = {
            "meta_improvement": 2.0,
            "code_review": 1.5,
            "security_audit": 1.5,
            "improvement_execution": 1.2,
        }
        return int(base * multipliers.get(task_type, 1.0))

    # ──────────────────────────────────────────────────────────── #
    # Step 4: EXECUTE                                               #
    # ──────────────────────────────────────────────────────────── #

    async def execute(
        self,
        task,  # AgentTask
        analysis: TaskAnalysis,
        agent_factory=None,  # agent_id → BaseAgent インスタンスを返すcallable
        *,
        record: bool = True,  # False の場合は呼び出し側が品質付きで記録する
    ) -> Any:
        """
        TaskAnalysis の計画に従ってエージェントを実行する。

        agent_factory が省略された場合は __init__ で生成したデフォルト
        AgentFactory.create を使用する。それも利用不可の場合のみ
        analysis オブジェクトをそのまま返す。

        実行所要時間を計測し、``record=True`` なら 1 回だけ
        ``_record_execution`` を呼ぶ（``record=False`` の場合は呼び出し側が
        レビュー由来の実 quality_score を付けて記録する）。

        Returns:
            AgentResult または analysis（factory なし）
        """
        if agent_factory is None:
            if self._agent_factory is not None:
                agent_factory = self._agent_factory.create
            else:
                logger.info(
                    "PreTaskOrchestrator: no agent_factory available, returning analysis only"
                )
                return analysis

        pattern = analysis.recommended_pattern
        self._exec_started_at = time.monotonic()
        # ルーティング中フラグを立て、選択エージェントの内部実行が再ルーティングしないようにする
        token = _ROUTING_ACTIVE.set(True)
        try:
            if pattern == OrchestrationPattern.SEQUENTIAL_PIPELINE:
                result = await self._execute_sequential(task, analysis, agent_factory)
            elif pattern == OrchestrationPattern.REVIEW_LOOP:
                result = await self._execute_review_loop(task, analysis, agent_factory)
            elif pattern == OrchestrationPattern.PARALLEL_THEN_MERGE:
                result = await self._execute_parallel(task, analysis, agent_factory)
            else:
                result = await self._execute_single(task, analysis, agent_factory)
        finally:
            _ROUTING_ACTIVE.reset(token)

        self._last_execution_ms = int((time.monotonic() - self._exec_started_at) * 1000)
        if record:
            self._record_execution(
                task, analysis, result, execution_time_ms=self._last_execution_ms
            )
        return result

    async def _execute_single(self, task, analysis, agent_factory):
        if not analysis.recommended_agent_ids:
            from agents.base import AgentResult

            return AgentResult(success=False, error="No agent selected")
        agent = agent_factory(analysis.recommended_agent_ids[0])
        if agent is None:
            from agents.base import AgentResult

            return AgentResult(
                success=False, error=f"Agent not found: {analysis.recommended_agent_ids[0]}"
            )
        result = await agent.run(task)
        return result

    async def _execute_sequential(self, task, analysis, agent_factory):
        """前工程の出力を次工程の入力に渡す逐次実行。"""
        import copy

        current_task = task
        last_result = None
        for agent_id in analysis.recommended_agent_ids:
            agent = agent_factory(agent_id)
            if agent is None:
                continue
            last_result = await agent.run(current_task)
            if not last_result.success:
                break
            # 前工程の出力を次工程の入力に追加
            enriched_input = copy.deepcopy(current_task.input)
            enriched_input["previous_output"] = last_result.output
            from agents.base import AgentTask

            current_task = AgentTask(
                task_type=current_task.task_type,
                description=current_task.description,
                input=enriched_input,
            )
        return last_result

    async def _execute_review_loop(self, task, analysis, agent_factory):
        """実行 → レビュー → (品質不足なら再実行) ループ。"""
        main_agent_id = (
            analysis.recommended_agent_ids[0] if analysis.recommended_agent_ids else None
        )
        if not main_agent_id:
            from agents.base import AgentResult

            return AgentResult(success=False, error="No main agent")
        agent = agent_factory(main_agent_id)
        if agent is None:
            from agents.base import AgentResult

            return AgentResult(success=False, error=f"Agent not found: {main_agent_id}")
        result = await agent.run(task)
        # レビューエージェントがあれば使う（なければそのまま返す）
        if len(analysis.recommended_agent_ids) > 1:
            reviewer_id = analysis.recommended_agent_ids[1]
            reviewer = agent_factory(reviewer_id)
            if reviewer:
                import copy

                review_task = copy.deepcopy(task)
                review_task.input["review_target"] = result.output
                await reviewer.run(review_task)
        return result

    async def _execute_parallel(self, task, analysis, agent_factory):
        """複数エージェントを並列実行して結果を統合する。"""
        agents = [
            agent_factory(aid)
            for aid in analysis.recommended_agent_ids
            if agent_factory(aid) is not None
        ]
        if not agents:
            from agents.base import AgentResult

            return AgentResult(success=False, error="No agents found")
        results = await asyncio.gather(*[a.run(task) for a in agents], return_exceptions=True)
        successful = [r for r in results if hasattr(r, "success") and r.success]
        if not successful:
            from agents.base import AgentResult

            return AgentResult(success=False, error="All parallel agents failed")
        # 最初の成功結果を代表として返す（将来: マージロジック）
        best = successful[0]
        return best

    # ──────────────────────────────────────────────────────────── #
    # Step 5: LEARN                                                 #
    # ──────────────────────────────────────────────────────────── #

    def _record_execution(
        self,
        task,
        analysis: TaskAnalysis,
        result,
        *,
        quality_score: float | None = None,
        execution_time_ms: int = 0,
    ) -> None:
        """実行結果をログに記録し、パターン検出器・パターンストア・能力レジストリに通知する。

        quality_score / execution_time_ms は呼び出し側（自己改善ループ等）が
        レビュー結果と計時から渡す。省略時は従来どおりのデフォルトで記録する。
        """
        success = getattr(result, "success", False)
        log_entry = {
            "task_type": analysis.task_type,
            "pattern_used": analysis.recommended_pattern,
            "agent_ids": analysis.recommended_agent_ids,
            "success": success,
            "quality_score": quality_score,
            "execution_time_ms": execution_time_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._execution_log.append(log_entry)

        # OrchestrationPatternStore に記録（パターン学習）— 実 quality/timing を反映
        if self._pattern_store:
            from core.orchestration.orchestration_pattern_store import PatternRecord

            try:
                self._pattern_store.record(
                    PatternRecord(
                        task_type=analysis.task_type,
                        pattern=analysis.recommended_pattern,
                        agent_ids=analysis.recommended_agent_ids,
                        success=success,
                        execution_time_ms=execution_time_ms,
                        quality_score=quality_score if quality_score is not None else 5.0,
                        notes=analysis.research_notes[:100],
                    )
                )
            except Exception as e:
                logger.debug("PatternStore record failed: %s", e)

        # CapabilityRegistry に使用実績を記録（次回の gap 分析・利用統計に反映）
        if self._registry and success:
            for aid in analysis.recommended_agent_ids:
                try:
                    self._registry.record_usage(aid)
                except Exception as e:  # noqa: BLE001
                    logger.debug("Capability usage record failed for %s: %s", aid, e)

        # OperationPatternDetector に記録
        if self._detector:
            try:
                self._detector.record_operation(
                    operation_type=analysis.task_type,
                    agent_name=",".join(analysis.recommended_agent_ids) or "unknown",
                    success=success,
                )
            except Exception as e:
                logger.debug("Pattern detection record failed: %s", e)

        # KnowledgeManager に成功パターンを保存
        if self._knowledge and success:
            try:
                self._knowledge.save_insight(
                    title=f"[Orchestration] {analysis.task_type}: {analysis.recommended_pattern}が有効",
                    content=(
                        f"パターン: {analysis.recommended_pattern}\n"
                        f"エージェント: {', '.join(analysis.recommended_agent_ids)}\n"
                        f"理由: {analysis.research_notes[:200]}"
                    ),
                    tags=["orchestration_pattern", analysis.task_type, "best_practice"],
                    importance="medium",
                )
            except Exception as e:
                logger.debug("Knowledge save failed: %s", e)

    def get_execution_log(self) -> List[Dict]:
        return list(self._execution_log)

    def get_pattern_summary(self) -> Dict[str, Any]:
        """どのオーケストレーションパターンが最もよく使われているかを集計する。"""
        from collections import Counter

        patterns = Counter(e["pattern_used"] for e in self._execution_log)
        successes = Counter(e["pattern_used"] for e in self._execution_log if e.get("success"))
        return {
            "total_executions": len(self._execution_log),
            "pattern_counts": dict(patterns),
            "pattern_success_counts": dict(successes),
        }

    # ──────────────────────────────────────────────────────────── #
    # 便利メソッド: analyze + execute の一括実行                    #
    # ──────────────────────────────────────────────────────────── #

    async def plan_and_execute(
        self,
        task_type: str,
        task,
        agent_factory=None,
        context: Optional[Dict] = None,
    ):
        """
        analyze() → execute() を一括実行する便利メソッド。
        全タスク実行の標準エントリポイント。
        """
        analysis = self.analyze(task_type, task.description, context=context)
        return await self.execute(task, analysis, agent_factory=agent_factory)
