"""
Internal Consultant - Strict Quality Reviewer

厳しい視点で、思考・実行・成果物・コスト効率・学習効率・再利用性を評価。
成功した場合でも「もっと良くできる」点を積極的に指摘する。
設定は config/default.yaml の self_improvement.review_strictness から読み込む。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from config.settings import load_config
from core.llm import LLMMessage, get_llm_provider
from core.models.organization import (
    ImprovementProposal,
    OrganizationMetrics,
    QualityReview,
    QualityScore,
)

logger = logging.getLogger(__name__)


STRICT_CONSULTANT_SYSTEM_PROMPT = """あなたは世界トップクラスの経営コンサルティングファーム（McKinsey / BCG）のシニアパートナーです。
あなたの役割は、どんなに優れた成果物・プロセスであっても、極めて厳しい視点で批判的に評価し、「さらに一段階上のレベル」に引き上げるための具体的な改善点を指摘することです。

以下の原則を厳守してください：
- 成功した場合でも「なぜもっと良くできないのか」を常に問う
- 曖昧な表現を許さず、具体的・定量的な指摘をする
- MECE（相互排他的・網羅的）な視点で分析する
- 「仮説→検証→改善」のサイクルを強く意識させる
- スコアは甘くせず、優秀なものでも7〜8点程度に留めるのが基本（10点はほぼ出さない）
- 改善提案は「実行可能でインパクトの大きいもの」を優先的に挙げる

評価する6つの軸：
1. Thinking Quality（思考の質）：仮説の鋭さ、選択肢の網羅性、論理の厳密さ
2. Execution Quality（実行の質）：効率性、ツール活用、ミスの少なさ、再現性
3. Output Quality（成果物の質）：正確性、完全性、保守性、影響力
4. Cost Efficiency（コスト効率）：トークン・時間・リソースの無駄の少なさ
5. Learning Efficiency（学習効率）：今回の活動からどれだけ組織や個人が学べたか
6. Reusability（再利用性）：他のタスク・エージェント・Organizationでどれだけ活用できるか

出力は必ず指定のJSON形式で厳密に行ってください。"""


async def run_strict_quality_review(
    task_description: str,
    thinking_process: str,
    execution_log: str,
    output_summary: str,
    cost_info: Optional[Dict[str, Any]] = None,
    context: Optional[str] = None,
    current_metrics: Optional[OrganizationMetrics] = None,
) -> QualityReview:
    """
    Internal Consultant が品質レビューを行う。
    current_metrics が渡された場合、YAML 設定の閾値に基づいてレビュー強度を動的に調整する。
    LLM の JSON 出力が不正な場合は最大 1 回リトライし、それでも失敗なら例外を送出する。
    """
    cfg = load_config().self_improvement
    provider = get_llm_provider("anthropic")

    strictness_instruction = ""
    if current_metrics:
        if current_metrics.health_score < cfg.review_strictness.low_health_threshold:
            strictness_instruction = (
                "\n【重要】この Organization の現在の健康度はかなり低いです。"
                "通常より一段階厳しく、根本的な問題点を容赦なく指摘してください。"
                "甘い評価は一切せず、組織の存続に関わるレベルの危機感を持ってレビューしてください。"
            )
        elif current_metrics.health_score < cfg.review_strictness.medium_health_threshold:
            strictness_instruction = (
                "\n【注意】この Organization の健康度がやや低い状態です。"
                "通常より厳しめの視点で、改善の余地を積極的に指摘してください。"
            )

    user_prompt = f"""以下のタスク・プロセス・成果物に対して、極めて厳格なコンサルタントとして評価してください。
{strictness_instruction}

【タスク概要】
{task_description}

【思考プロセス】
{thinking_process}

【実行ログ・方法】
{execution_log}

【成果物サマリー】
{output_summary}

【コスト情報（利用可能な場合）】
{cost_info or "情報なし"}

【その他文脈】
{context or "特になし"}

上記の内容を、6つの評価軸で1〜10点で厳しく採点し、批判的コメントと改善機会を抽出してください。
成功していても「もっと良くできる」点を必ず指摘してください。

出力は以下のJSON形式で厳密に返してください（マークダウンや説明文は不要）：
{{
  "overall_score": <1-10の数値>,
  "dimension_scores": [
    {{"dimension": "thinking_quality", "score": <数値>, "comment": "<厳しい指摘>", "evidence": "<根拠>"}},
    ...
  ],
  "critical_findings": ["<特に厳しく指摘する点1>", ...],
  "improvement_opportunities": ["<成功時でも改善できる点1>", ...],
  "consultant_comment": "<トップコンサルタントらしい全体コメント>"
}}
"""

    messages = [
        LLMMessage(role="system", content=STRICT_CONSULTANT_SYSTEM_PROMPT),
        LLMMessage(role="user", content=user_prompt),
    ]

    data = await _generate_and_parse_json(provider, messages)

    dimension_scores = [QualityScore(**item) for item in data.get("dimension_scores", [])]

    review = QualityReview(
        overall_score=data.get("overall_score", 5.0),
        dimension_scores=dimension_scores,
        critical_findings=data.get("critical_findings", []),
        improvement_opportunities=data.get("improvement_opportunities", []),
        consultant_comment=data.get("consultant_comment", ""),
        target_type="general_task",
    )

    return review


async def _generate_and_parse_json(provider, messages: list, max_retries: int = 2) -> dict:
    """LLM を呼んで JSON をパースする。失敗時は max_retries 回リトライし、それでも失敗なら例外を送出。"""
    last_error: Exception | None = None
    for attempt in range(max_retries):
        response = await provider.generate(
            messages=messages,
            temperature=0.3,
            max_tokens=4000,
            task_type="quality_review",
        )
        try:
            # コードブロック等のラッパーを除去してからパース
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(
                "Internal Consultant: JSON parse failed (attempt %d/%d): %s",
                attempt + 1,
                max_retries,
                e,
            )

    raise RuntimeError(
        f"Internal Consultant: JSON parse failed after {max_retries} attempts. Last error: {last_error}"
    ) from last_error


def generate_improvement_proposals_from_review(review: QualityReview) -> List[ImprovementProposal]:
    """レビュー結果から改善提案を自動生成（簡易版）"""
    proposals = []
    for i, opportunity in enumerate(review.improvement_opportunities[:3]):  # 上位3つ
        proposals.append(
            ImprovementProposal(
                review_id=review.id,
                priority="high" if review.overall_score < 6 else "medium",
                category="general",
                title=f"改善提案 {i + 1}",
                description=opportunity,
                expected_impact="組織全体の品質・効率向上",
                implementation_difficulty="medium",
            )
        )
    return proposals
