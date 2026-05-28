"""
BestPracticeAdvisor — タスク実行前ベストプラクティス参照 (N-05)

PreTaskOrchestrator の「RESEARCH」フェーズ専用モジュール。

KnowledgeManager の過去実行ログ + OrchestrationPatternStore の統計から
「このタスクをこう実行したら成功した」パターンを取得して
TaskAnalysis.research_notes に注入する。

これにより、システムは同種タスクを繰り返すたびに
過去の経験を活かしてより賢く実行できるようになる。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BestPracticeAdvisor:
    """
    タスク開始前に実行される「知識調査エージェント」。

    参照源:
    1. KnowledgeManager — 過去のエージェント実行から保存された知見
    2. OrchestrationPatternStore — パターン統計（成功率・品質スコア）
    3. タスク種別の静的ベストプラクティス定義（フォールバック）
    """

    # タスク種別ごとの静的ベストプラクティス（Knowledge がない時のフォールバック）
    STATIC_BEST_PRACTICES: Dict[str, str] = {
        "code_review": (
            "【ベストプラクティス】\n"
            "1. まず CodebaseExplorerAgent でコードベース全体を把握する\n"
            "2. CodeReviewAgent でスキルベースの詳細レビューを行う\n"
            "3. InternalConsultant で最終品質チェックを行う\n"
            "4. 過去の承認・却下パターンをナレッジから参照して傾向を把握する\n"
            "推奨パターン: ReviewLoop（実行→レビュー→品質確認）"
        ),
        "improvement_execution": (
            "【ベストプラクティス】\n"
            "1. 変更対象ファイルを必ずバックアップする\n"
            "2. 変更前後でテストを実行して回帰がないことを確認する\n"
            "3. 複数ファイルにまたがる変更は依存関係を分析してから実施する\n"
            "推奨パターン: SequentialPipeline（バックアップ→変更→テスト）"
        ),
        "codebase_exploration": (
            "【ベストプラクティス】\n"
            "1. CodebaseIndexer のキャッシュを使い、全スキャンを避ける\n"
            "2. 目的別スナップショット（exploration/improvement/security）を使い分ける\n"
            "3. 調査結果はナレッジに保存して次回の調査コストを削減する\n"
            "推奨パターン: SingleAgent（CodebaseExplorerAgent 単独）"
        ),
        "meta_improvement": (
            "【ベストプラクティス】\n"
            "1. まずメトリクスを収集して「どの組織が最も改善を必要としているか」を判断する\n"
            "2. Human-in-the-Loop を必ず設ける（システム自体への変更は慎重に）\n"
            "3. Meta-Improvement の提案は小さく・安全に・段階的に\n"
            "推奨パターン: Hierarchical（マネージャーが複数ワーカーを指揮）"
        ),
        "security_audit": (
            "【ベストプラクティス】\n"
            "1. 認証・設定ファイル・環境変数を最優先で確認する\n"
            "2. TOOL_INTEGRATION スキルを持つエージェントを使う\n"
            "3. 発見された問題は即座にHIGH/MEDIUM/LOWで分類する\n"
            "推奨パターン: ReviewLoop（スキャン→詳細分析→優先度付け）"
        ),
    }

    def __init__(
        self,
        knowledge_manager=None,
        pattern_store=None,
    ):
        self._knowledge = knowledge_manager
        self._pattern_store = pattern_store

    def advise(self, task_type: str, description: str = "") -> str:
        """
        タスクに対するベストプラクティスアドバイスを返す。

        優先順:
        1. KnowledgeManager から関連知識（過去実績ベース）
        2. OrchestrationPatternStore から成功パターン統計
        3. 静的ベストプラクティス（フォールバック）
        """
        sections = []

        # 1. KnowledgeManager から過去実績を取得
        if self._knowledge:
            knowledge_text = self._knowledge.get_context_for_agent(
                tags=[task_type, "orchestration_pattern", "best_practice"],
                limit=3,
            )
            if knowledge_text:
                sections.append(knowledge_text)

        # 2. OrchestrationPatternStore から統計
        if self._pattern_store:
            stats_text = self._format_pattern_stats(task_type)
            if stats_text:
                sections.append(stats_text)

        # 3. 静的フォールバック（Knowledge がない場合でも必ず何かを提供）
        if not sections:
            static = self.STATIC_BEST_PRACTICES.get(task_type)
            if static:
                sections.append(static)

        if not sections:
            return ""

        return "\n\n".join(sections)

    def _format_pattern_stats(self, task_type: str) -> str:
        """パターン統計を人間が読める形式に変換する。"""
        if not self._pattern_store:
            return ""
        stats = self._pattern_store.get_stats_for_task(task_type)
        if not stats:
            return ""

        lines = [f"【{task_type} の実行実績】"]
        for s in sorted(stats, key=lambda x: x.success_rate, reverse=True):
            recommended = " ★推奨" if s.recommended else ""
            lines.append(
                f"  - {s.pattern}: 実行{s.total_runs}回, "
                f"成功率{s.success_rate:.0%}, "
                f"平均品質{s.avg_quality:.1f}/10{recommended}"
            )
        return "\n".join(lines)
