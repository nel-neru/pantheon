"""
Task実行 + Strict Quality Review の自動トリガー機構

これにより、主要なタスク完了後に必ずInternal Consultantによる
厳格なレビューが走り、成功時でも改善提案が生成される。
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional

from core.models.organization import ImprovementProposal, QualityReview
from core.quality.internal_consultant import (
    generate_improvement_proposals_from_review,
    run_strict_quality_review,
)


async def execute_task_with_strict_review(
    task_func: Callable[[], Awaitable[Any]],
    task_description: str,
    thinking_process: str = "",
    execution_log: str = "",
    output_summary: str = "",
    cost_info: Optional[Dict[str, Any]] = None,
    context: Optional[str] = None,
) -> tuple[Any, QualityReview, list[ImprovementProposal]]:
    """
    タスクを実行した後、自動でかなり厳しめの品質レビューを行い、
    改善提案を生成する。

    Returns:
        (task_result, quality_review, improvement_proposals)
    """
    # 1. タスク実行
    print(f"[Trigger] タスク実行開始: {task_description[:60]}...")
    task_result = await task_func()
    print("[Trigger] タスク完了。厳格レビューを開始します...")

    # 2. 実行ログなどを自動補完（簡易版）
    if not execution_log:
        execution_log = f"Task '{task_description}' was executed."

    if not output_summary:
        output_summary = str(task_result)[:500] if task_result else "No output"

    # 3. 厳格レビュー実行
    review: QualityReview = await run_strict_quality_review(
        task_description=task_description,
        thinking_process=thinking_process or "Thinking process not provided in detail.",
        execution_log=execution_log,
        output_summary=output_summary,
        cost_info=cost_info,
        context=context,
    )

    # 4. 改善提案の自動生成
    proposals: list[ImprovementProposal] = generate_improvement_proposals_from_review(review)

    print(f"[Trigger] レビュー完了 | Overall Score: {review.overall_score:.1f}/10")
    print(f"[Trigger] 改善提案 {len(proposals)}件 生成")

    return task_result, review, proposals


# 使用例（将来的にワーカーやワークフローから呼び出す）
async def example_usage():
    async def sample_task():
        await asyncio.sleep(0.1)
        return {"status": "success", "value": 42}

    result, review, proposals = await execute_task_with_strict_review(
        task_func=sample_task,
        task_description="サンプルタスクの実行と結果のまとめ",
        thinking_process="タスクを分解し、効率的な方法を選択した",
        context="これはテスト用の例です",
    )

    print("\n=== Review Result ===")
    print(f"Overall: {review.overall_score}")
    print(f"Consultant Comment: {review.consultant_comment[:200]}...")
    for p in proposals:
        print(f"- Proposal: {p.title} ({p.priority})")
