"""
GoalVerifier — 目標達成検証 (M-05)

ExecutionCoordinator の実行が完了した後、
目標の成功基準が実際に達成されているかを評価する。

評価方法:
  - 成功基準に対してルールベース + オプション LLM で達成度を評価
  - 客観指標（実行完了タスク数、テスト結果など）を活用
  - 未達成の場合は残タスクの再実行を提案
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.goals.execution_coordinator import ExecutionProgress, TaskStatus
from core.goals.goal_decomposer import GoalPlan
from core.goals.goal_parser import StructuredGoal

logger = logging.getLogger(__name__)


@dataclass
class CriterionResult:
    """成功基準1件の評価結果。"""
    criterion: str
    met: bool
    confidence: float = 0.0    # 0.0〜1.0
    evidence: str = ""


@dataclass
class GoalVerificationResult:
    """目標達成検証の総合結果。"""
    goal_id: str
    goal_description: str
    overall_achieved: bool
    achievement_pct: float                          # 0〜100
    criterion_results: List[CriterionResult] = field(default_factory=list)
    unmet_criteria: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    verified_at: str = ""

    def __post_init__(self):
        if not self.verified_at:
            self.verified_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "goal_description": self.goal_description,
            "overall_achieved": self.overall_achieved,
            "achievement_pct": self.achievement_pct,
            "criterion_results": [
                {"criterion": r.criterion, "met": r.met, "evidence": r.evidence}
                for r in self.criterion_results
            ],
            "unmet_criteria": self.unmet_criteria,
            "recommendations": self.recommendations,
            "verified_at": self.verified_at,
        }


class GoalVerifier:
    """
    目標の達成度を評価するクラス。

    ExecutionProgress と StructuredGoal の成功基準を突き合わせて
    達成度 (0〜100%) を算出する。
    """

    ACHIEVEMENT_THRESHOLD = 70.0    # この%以上で「達成」とみなす

    def __init__(self, llm_client: Optional[Any] = None):
        self._llm = llm_client

    def verify(
        self,
        goal: StructuredGoal,
        plan: GoalPlan,
        execution_progress: ExecutionProgress,
        use_llm: bool = False,
    ) -> GoalVerificationResult:
        """
        目標達成度を評価する。

        Args:
            goal: 元の構造化された目標
            plan: 実行計画
            execution_progress: 実行結果
            use_llm: LLM による追加評価を行うか

        Returns:
            GoalVerificationResult
        """
        criterion_results = self._evaluate_criteria(goal, execution_progress)

        met_count = sum(1 for r in criterion_results if r.met)
        total = len(criterion_results) or 1
        achievement_pct = met_count / total * 100

        # タスク完了率も考慮（ボーナス/ペナルティ）
        task_completion_rate = execution_progress.progress_pct / 100
        achievement_pct = achievement_pct * 0.7 + task_completion_rate * 100 * 0.3
        achievement_pct = min(100.0, max(0.0, achievement_pct))

        unmet = [r.criterion for r in criterion_results if not r.met]
        recommendations = self._generate_recommendations(
            goal, unmet, execution_progress
        )

        if use_llm and self._llm:
            try:
                llm_boost = self._verify_with_llm(goal, execution_progress)
                achievement_pct = min(100.0, (achievement_pct + llm_boost) / 2)
            except Exception as e:
                logger.warning("LLM verification failed: %s", e)

        return GoalVerificationResult(
            goal_id=goal.goal_id,
            goal_description=goal.description,
            overall_achieved=achievement_pct >= self.ACHIEVEMENT_THRESHOLD,
            achievement_pct=achievement_pct,
            criterion_results=criterion_results,
            unmet_criteria=unmet,
            recommendations=recommendations,
        )

    def _evaluate_criteria(
        self,
        goal: StructuredGoal,
        progress: ExecutionProgress,
    ) -> List[CriterionResult]:
        """各成功基準を実行結果から評価する。"""
        results: List[CriterionResult] = []

        for criterion in goal.success_criteria:
            met, confidence, evidence = self._check_criterion(criterion, progress)
            results.append(CriterionResult(
                criterion=criterion,
                met=met,
                confidence=confidence,
                evidence=evidence,
            ))

        # 基準がない場合はタスク完了率のみで評価
        if not results:
            met = progress.progress_pct >= 80
            results.append(CriterionResult(
                criterion="タスクが80%以上完了している",
                met=met,
                confidence=0.9,
                evidence=f"タスク完了率: {progress.progress_pct:.1f}%",
            ))

        return results

    def _check_criterion(
        self,
        criterion: str,
        progress: ExecutionProgress,
    ) -> tuple:
        """成功基準1件を判定し (met, confidence, evidence) を返す。"""
        c_lower = criterion.lower()

        # タスク完了率チェック
        if "完了" in criterion or "パス" in criterion or "pass" in c_lower:
            met = progress.progress_pct >= 80
            evidence = f"タスク完了率: {progress.progress_pct:.1f}% ({progress.done_count}/{progress.total})"
            return met, 0.8, evidence

        # テスト関連
        if "テスト" in criterion or "test" in c_lower:
            done_tasks = [
                p for p in progress.task_progresses.values()
                if p.status == TaskStatus.DONE and "テスト" in p.title
            ]
            met = len(done_tasks) > 0
            evidence = f"テスト関連タスク完了: {len(done_tasks)} 件"
            return met, 0.7, evidence

        # 失敗タスクなし
        if "エラー" in criterion or "error" in c_lower or "失敗" in criterion:
            met = progress.failed_count == 0
            evidence = f"失敗タスク: {progress.failed_count} 件"
            return met, 0.9, evidence

        # デフォルト: タスク完了率で判定
        met = progress.progress_pct >= 70
        evidence = f"タスク進捗: {progress.progress_pct:.1f}%"
        return met, 0.5, evidence

    def _generate_recommendations(
        self,
        goal: StructuredGoal,
        unmet_criteria: List[str],
        progress: ExecutionProgress,
    ) -> List[str]:
        """未達成基準に対する改善推奨事項を生成する。"""
        recs: List[str] = []

        if unmet_criteria:
            recs.append(f"未達成の成功基準 {len(unmet_criteria)} 件を重点的に対処してください")
            for c in unmet_criteria[:3]:
                recs.append(f"  → {c}")

        if progress.failed_count > 0:
            failed = [
                p.title for p in progress.task_progresses.values()
                if p.status == TaskStatus.FAILED
            ]
            recs.append(f"失敗したタスク ({progress.failed_count} 件) を再実行してください:")
            for title in failed[:3]:
                recs.append(f"  → {title}")

        skipped = [
            p for p in progress.task_progresses.values()
            if p.status == TaskStatus.SKIPPED and "能力" in p.error
        ]
        if skipped:
            recs.append(
                f"{len(skipped)} 件のタスクがエージェント能力不足でスキップされました。"
                f"repocorp orchestration capabilities でギャップを確認してください。"
            )

        if not recs:
            recs.append("目標は達成されています。次の目標を設定してください。")

        return recs

    def _verify_with_llm(
        self,
        goal: StructuredGoal,
        progress: ExecutionProgress,
    ) -> float:
        """LLM による達成度評価 (0〜100 を返す)。"""
        prompt = f"""以下の目標の達成状況を評価してください。

目標: {goal.description}
成功基準:
{chr(10).join(f'- {c}' for c in goal.success_criteria)}

実行結果:
- 総タスク数: {progress.total}
- 完了: {progress.done_count}
- 失敗: {progress.failed_count}
- 完了率: {progress.progress_pct:.1f}%

0〜100の数値のみで達成度を答えてください（例: 75）"""

        response = self._llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        import re
        match = re.search(r'\d+', content)
        if match:
            return float(min(100, max(0, int(match.group()))))
        return 50.0
