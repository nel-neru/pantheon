"""
TokenBudgetManager — トークン予算管理 (K-11)

各タスク種別に応じたトークン予算を定義し、コンテキスト生成時に
予算内に収まるよう自動制御する。

予算超過によるLLMエラーをゼロにしながら、各タスクに適切な
情報密度を確保することが目的。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class TokenBudget:
    """タスク種別のトークン予算定義。"""
    task_type: str
    max_context_tokens: int       # コンテキスト（コードベース情報等）上限
    max_prompt_tokens: int        # プロンプト全体上限
    max_output_tokens: int        # 出力上限
    snapshot_mode: str = "exploration"
    description: str = ""


# デフォルト予算テーブル
DEFAULT_BUDGETS: Dict[str, TokenBudget] = {
    "code_review": TokenBudget(
        task_type="code_review",
        max_context_tokens=8_000,
        max_prompt_tokens=12_000,
        max_output_tokens=3_000,
        snapshot_mode="code_review",
        description="コードレビュー: エントリポイントと主要クラスを網羅",
    ),
    "improvement_execution": TokenBudget(
        task_type="improvement_execution",
        max_context_tokens=6_000,
        max_prompt_tokens=10_000,
        max_output_tokens=8_000,
        snapshot_mode="improvement",
        description="改善実行: 変更対象ファイルとその依存関係を優先",
    ),
    "quality_review": TokenBudget(
        task_type="quality_review",
        max_context_tokens=4_000,
        max_prompt_tokens=8_000,
        max_output_tokens=4_000,
        snapshot_mode="code_review",
        description="品質レビュー: コアモジュールと品質指標を優先",
    ),
    "codebase_exploration": TokenBudget(
        task_type="codebase_exploration",
        max_context_tokens=3_000,
        max_prompt_tokens=5_000,
        max_output_tokens=2_000,
        snapshot_mode="exploration",
        description="コードベース調査: 全体構造の俯瞰を最小トークンで",
    ),
    "meta_improvement": TokenBudget(
        task_type="meta_improvement",
        max_context_tokens=10_000,
        max_prompt_tokens=15_000,
        max_output_tokens=5_000,
        snapshot_mode="meta_improvement",
        description="メタ改善: アーキテクチャ全体を把握",
    ),
    "security_audit": TokenBudget(
        task_type="security_audit",
        max_context_tokens=6_000,
        max_prompt_tokens=10_000,
        max_output_tokens=3_000,
        snapshot_mode="security",
        description="セキュリティ監査: 認証・設定ファイルを優先",
    ),
    "conversation": TokenBudget(
        task_type="conversation",
        max_context_tokens=2_000,
        max_prompt_tokens=4_000,
        max_output_tokens=1_000,
        snapshot_mode="exploration",
        description="対話モード: 軽量コンテキストで素早く応答",
    ),
    "default": TokenBudget(
        task_type="default",
        max_context_tokens=4_000,
        max_prompt_tokens=8_000,
        max_output_tokens=3_000,
        snapshot_mode="exploration",
        description="デフォルト予算",
    ),
}


@dataclass
class TokenUsageRecord:
    """トークン使用実績記録。予算の自動最適化に使用する。"""
    task_type: str
    actual_context_tokens: int
    actual_prompt_tokens: int
    actual_output_tokens: int
    task_success: bool
    timestamp: str = ""


class TokenBudgetManager:
    """
    タスク種別ごとのトークン予算を管理する。

    - 予算定義の取得
    - コンテキスト文字列のトリミング
    - 使用実績の記録と予算自動調整（将来）
    """

    def __init__(self, custom_budgets: Optional[Dict[str, TokenBudget]] = None):
        self._budgets = {**DEFAULT_BUDGETS, **(custom_budgets or {})}
        self._usage_history: list[TokenUsageRecord] = []

    def get_budget(self, task_type: str) -> TokenBudget:
        """タスク種別の予算を返す。未定義の場合はデフォルト予算。"""
        return self._budgets.get(task_type, self._budgets["default"])

    def fit_context(self, context: str, task_type: str) -> str:
        """
        コンテキスト文字列をトークン予算内に収める。
        1トークン ≒ 4文字 として計算。
        """
        budget = self.get_budget(task_type)
        max_chars = budget.max_context_tokens * 4

        if len(context) <= max_chars:
            return context

        truncated = context[:max_chars]
        logger.debug(
            "TokenBudgetManager: %s コンテキストを %d文字 → %d文字 にトリミング",
            task_type, len(context), max_chars,
        )
        return truncated + f"\n... (トークン上限 {budget.max_context_tokens} により省略)"

    def estimate_tokens(self, text: str) -> int:
        """テキストのトークン数を概算する（1トークン ≒ 4文字）。"""
        return max(1, len(text) // 4)

    def get_snapshot_mode(self, task_type: str) -> str:
        """タスクに適したスナップショットモードを返す。"""
        return self.get_budget(task_type).snapshot_mode

    def record_usage(
        self,
        task_type: str,
        context_tokens: int,
        prompt_tokens: int,
        output_tokens: int,
        success: bool,
    ) -> None:
        """実際のトークン使用量を記録する。"""
        from datetime import datetime, timezone
        record = TokenUsageRecord(
            task_type=task_type,
            actual_context_tokens=context_tokens,
            actual_prompt_tokens=prompt_tokens,
            actual_output_tokens=output_tokens,
            task_success=success,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._usage_history.append(record)

    def get_usage_summary(self) -> Dict[str, Any]:
        """タスク種別ごとの平均トークン使用量を返す。"""
        summary: Dict[str, Dict[str, Any]] = {}
        for rec in self._usage_history:
            if rec.task_type not in summary:
                summary[rec.task_type] = {
                    "count": 0,
                    "avg_context": 0,
                    "avg_prompt": 0,
                    "avg_output": 0,
                    "success_rate": 0,
                }
            s = summary[rec.task_type]
            n = s["count"]
            s["avg_context"] = (s["avg_context"] * n + rec.actual_context_tokens) / (n + 1)
            s["avg_prompt"] = (s["avg_prompt"] * n + rec.actual_prompt_tokens) / (n + 1)
            s["avg_output"] = (s["avg_output"] * n + rec.actual_output_tokens) / (n + 1)
            s["success_rate"] = (s["success_rate"] * n + int(rec.task_success)) / (n + 1)
            s["count"] += 1

        return summary

    def list_budgets(self) -> Dict[str, Dict[str, Any]]:
        """全予算設定を辞書で返す。"""
        return {
            name: {
                "max_context_tokens": b.max_context_tokens,
                "max_prompt_tokens": b.max_prompt_tokens,
                "max_output_tokens": b.max_output_tokens,
                "snapshot_mode": b.snapshot_mode,
                "description": b.description,
            }
            for name, b in self._budgets.items()
        }


# モジュールレベルのシングルトン（各エージェントが共有）
_default_manager = TokenBudgetManager()


def get_token_budget_manager() -> TokenBudgetManager:
    """デフォルトのTokenBudgetManagerを返す。"""
    return _default_manager
