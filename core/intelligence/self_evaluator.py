"""
AgentSelfEvaluator — エージェント自己評価 (A-10)
エージェントが自分の出力を採点し、低品質なら再試行する
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable


@dataclass
class EvaluationResult:
    score: float
    feedback: str
    should_retry: bool


class AgentSelfEvaluator:
    """LLMを使わないヒューリスティックな自己評価器。"""

    FILE_OR_LINE_PATTERN = re.compile(r"(?:\b[\w./-]+\.[\w]+(?::\d+)?\b|\bline\s+\d+\b|\bL\d+\b)", re.IGNORECASE)
    BULLET_PATTERN = re.compile(r"(^\s*[-*•]\s+)|(^\s*\d+[.)]\s+)", re.MULTILINE)

    def evaluate(self, output: str, task_type: str) -> EvaluationResult:
        _ = task_type
        text = output or ""
        score = 0.0
        feedback: list[str] = []

        if len(text) > 100:
            score += 2.0
            feedback.append("十分な説明量があります")
        if self.FILE_OR_LINE_PATTERN.search(text):
            score += 2.0
            feedback.append("具体的なファイルや行番号があります")
        if any(keyword in text for keyword in ["改善", "suggest", "proposal"]):
            score += 2.0
            feedback.append("改善提案が含まれています")
        if self.BULLET_PATTERN.search(text):
            score += 2.0
            feedback.append("構造化された箇条書きがあります")

        unresolved_error = (
            ("エラー" in text or "失敗" in text)
            and not any(keyword in text for keyword in ["解決", "対応", "resolved", "修正"])
        )
        if not unresolved_error:
            score += 2.0
            feedback.append("未解決エラーが見当たりません")
        else:
            feedback.append("未解決エラー表現があります")

        should_retry = score < 4.0
        return EvaluationResult(
            score=score,
            feedback=" / ".join(feedback) if feedback else "改善の余地があります",
            should_retry=should_retry,
        )

    def evaluate_with_retry(
        self,
        generate_fn: Callable[[], str],
        task_type: str,
        max_retries: int = 2,
    ) -> tuple[str, EvaluationResult]:
        attempts = 0
        last_output = ""
        last_evaluation = EvaluationResult(score=0.0, feedback="未評価", should_retry=True)

        while attempts <= max_retries:
            last_output = generate_fn()
            last_evaluation = self.evaluate(last_output, task_type)
            if not last_evaluation.should_retry:
                return last_output, last_evaluation
            attempts += 1

        return last_output, last_evaluation
