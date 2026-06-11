"""
ScoreUpdater — Organization スコア自動更新 (C-01~C-03)

`autonomy_score` と `improvement_velocity` が一度も更新されない
という課題を解消する。

エージェント実行の結果（成功/失敗・提案数・品質スコア）を受け取り、
Organization の成長スコアをリアルタイムに更新する。

これにより「共進化」が数値で見えるようになる。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from core.models.organization import Organization

logger = logging.getLogger(__name__)


@dataclass
class ExecutionOutcome:
    """
    1回のエージェント実行の結果サマリー。
    ScoreUpdater はこの構造体を受け取ってスコアを計算する。
    """

    success: bool
    suggestions_count: int = 0  # 生成した提案数
    accepted_suggestions: int = 0  # 承認された提案数
    quality_score: float = 5.0  # 提案品質スコア (0~10)
    execution_time_ms: int = 0
    used_cached_knowledge: bool = False  # 知識ループを活用したか
    self_initiated: bool = False  # システムが自律的に開始したか


class ScoreUpdater:
    """
    実行結果に基づいて Organization のスコアを更新する。

    更新ロジック:
    - autonomy_score: 自律実行の成功頻度・自己開始率で上昇
    - improvement_velocity: 提案の生成・採用速度で上昇
    - 両スコアは [0, 100] の範囲にクランプされる
    - 指数移動平均 (EMA) で急激な変動を抑制

    EMA 係数 alpha=0.2 → 直近5回の実行で約 70% の重みが決まる
    """

    EMA_ALPHA = 0.2  # 指数移動平均の平滑化係数
    BASE_AUTONOMY_GAIN = 2.0  # 成功1回あたりの自律スコア基本増加量
    BASE_VELOCITY_GAIN = 1.5  # 提案1件あたりの速度スコア基本増加量
    KNOWLEDGE_BONUS = 1.0  # 知識ループ活用ボーナス
    SELF_INITIATED_BONUS = 2.0  # 自律起動ボーナス
    FAILURE_PENALTY = 3.0  # 失敗時のペナルティ

    def update(
        self,
        organization: Organization,
        outcome: ExecutionOutcome,
        state_manager=None,
    ) -> Organization:
        """
        実行結果に基づいて Organization のスコアをインプレース更新し、
        永続化まで行う。

        Args:
            organization: 更新対象の Organization
            outcome: 実行結果
            state_manager: RepoStateManager（永続化用、省略可）

        Returns:
            更新後の Organization（同一オブジェクト）
        """
        old_autonomy = organization.autonomy_score
        old_velocity = organization.improvement_velocity

        # ── autonomy_score の更新 ──
        if outcome.success:
            autonomy_delta = self.BASE_AUTONOMY_GAIN
            if outcome.self_initiated:
                autonomy_delta += self.SELF_INITIATED_BONUS
            if outcome.used_cached_knowledge:
                autonomy_delta += self.KNOWLEDGE_BONUS
            new_autonomy = self._ema_update(old_autonomy, old_autonomy + autonomy_delta)
        else:
            new_autonomy = self._ema_update(old_autonomy, old_autonomy - self.FAILURE_PENALTY)

        # ── improvement_velocity の更新 ──
        if outcome.success and outcome.suggestions_count > 0:
            velocity_delta = (
                self.BASE_VELOCITY_GAIN * outcome.suggestions_count
                + outcome.accepted_suggestions * 2.0
                + (outcome.quality_score - 5.0) * 0.5
            )
            new_velocity = self._ema_update(old_velocity, old_velocity + velocity_delta)
        elif not outcome.success:
            new_velocity = self._ema_update(old_velocity, old_velocity - self.FAILURE_PENALTY)
        else:
            new_velocity = old_velocity

        # クランプ [0, 100]
        organization.autonomy_score = round(max(0.0, min(100.0, new_autonomy)), 1)
        organization.improvement_velocity = round(max(0.0, min(100.0, new_velocity)), 1)

        # 更新日時を記録
        from datetime import datetime, timezone

        organization.last_active = datetime.now(timezone.utc)

        logger.debug(
            "ScoreUpdater: %s autonomy %.1f→%.1f velocity %.1f→%.1f",
            organization.name,
            old_autonomy,
            organization.autonomy_score,
            old_velocity,
            organization.improvement_velocity,
        )

        # 永続化
        if state_manager is not None:
            try:
                state_manager.save_organization(organization)
            except Exception as e:
                logger.warning("ScoreUpdater: 永続化に失敗: %s", e)

        return organization

    def _ema_update(self, current: float, new_value: float) -> float:
        """指数移動平均で急激な変動を抑制する。"""
        return self.EMA_ALPHA * new_value + (1 - self.EMA_ALPHA) * current

    @staticmethod
    def outcome_from_agent_result(
        result,
        accepted_suggestions: int = 0,
        self_initiated: bool = False,
        quality_score: Optional[float] = None,
    ) -> ExecutionOutcome:
        """
        AgentResult から ExecutionOutcome を生成するユーティリティ。

        Args:
            result: AgentResult インスタンス
            accepted_suggestions: 承認された提案数
            self_initiated: システムが自律的に起動したか
            quality_score: 外部からスコアが渡された場合に使用
        """
        suggestions = result.output.get("suggestions", []) if result.output else []
        return ExecutionOutcome(
            success=result.success,
            suggestions_count=len(suggestions),
            accepted_suggestions=accepted_suggestions,
            quality_score=quality_score or 5.0,
            used_cached_knowledge=result.output.get("knowledge_injected", False)
            if result.output
            else False,
            self_initiated=self_initiated,
        )
