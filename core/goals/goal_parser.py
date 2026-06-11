"""
GoalParser — 自然言語目標パーサー (M-01)

「Eコマースサイトを作りたい」「このAPIをREST化したい」等の
自然言語ゴールを構造化された Goal オブジェクトに変換する。

入力: 自然言語の目標テキスト
出力: StructuredGoal（種別・スコープ・制約・成功基準・推定規模）
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────── #
# データモデル                                                         #
# ────────────────────────────────────────────────────────────────── #


class GoalType:
    """目標の種別定数。"""

    NEW_SERVICE = "new_service"  # 新サービス・アプリの作成
    IMPROVEMENT = "improvement"  # 既存コードの改善
    SECURITY = "security"  # セキュリティ強化
    PERFORMANCE = "performance"  # パフォーマンス改善
    TEST_COVERAGE = "test_coverage"  # テストカバレッジ向上
    REFACTORING = "refactoring"  # リファクタリング
    DOCUMENTATION = "documentation"  # ドキュメント整備
    MIGRATION = "migration"  # 移行・アップグレード
    AUTOMATION = "automation"  # 自動化
    GENERAL = "general"  # その他


class GoalScale:
    """目標の規模定数。"""

    SMALL = "small"  # 1〜2日
    MEDIUM = "medium"  # 1〜2週間
    LARGE = "large"  # 1ヶ月以上


@dataclass
class StructuredGoal:
    """パース済みの構造化された目標。"""

    goal_id: str
    raw_text: str
    goal_type: str
    scope: str  # 変更範囲（"repository", "module", "function"）
    description: str  # 1〜2文の明確な目標記述
    success_criteria: List[str]  # 達成判定基準（箇条書き）
    constraints: List[str]  # 制約（後方互換性維持 etc.）
    suggested_categories: List[str]  # 関連するImprovementProposalカテゴリ
    scale: str = GoalScale.MEDIUM
    domain: str = ""  # ドメイン（ecommerce, api, cli etc.）
    features: List[str] = field(default_factory=list)
    parsed_at: str = ""

    def __post_init__(self):
        if not self.parsed_at:
            self.parsed_at = datetime.now(timezone.utc).isoformat()
        if not self.goal_id:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            self.goal_id = f"goal:{self.goal_type}:{ts}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "raw_text": self.raw_text,
            "goal_type": self.goal_type,
            "scope": self.scope,
            "description": self.description,
            "success_criteria": self.success_criteria,
            "constraints": self.constraints,
            "suggested_categories": self.suggested_categories,
            "scale": self.scale,
            "domain": self.domain,
            "features": self.features,
            "parsed_at": self.parsed_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StructuredGoal":
        allowed = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in allowed})


# ────────────────────────────────────────────────────────────────── #
# ルールベース分類器                                                   #
# ────────────────────────────────────────────────────────────────── #

# (キーワードリスト, GoalType, スコープ, ドメイン, 成功基準テンプレート)
_CLASSIFICATION_RULES: List[Dict[str, Any]] = [
    {
        "keywords": ["セキュリティ", "security", "脆弱性", "vulnerability", "認証", "auth"],
        "goal_type": GoalType.SECURITY,
        "scope": "module",
        "categories": ["security"],
        "criteria": [
            "既知の脆弱性パターンが解消されている",
            "セキュリティ監査ツールでエラーが出ない",
        ],
    },
    {
        "keywords": ["テスト", "test", "カバレッジ", "coverage", "pytest", "unittest"],
        "goal_type": GoalType.TEST_COVERAGE,
        "scope": "repository",
        "categories": ["testing"],
        "criteria": ["テストカバレッジが目標値以上になっている", "CI/CDがパスする"],
    },
    {
        "keywords": [
            "パフォーマンス",
            "performance",
            "速度",
            "speed",
            "最適化",
            "optimize",
            "遅い",
            "slow",
        ],
        "goal_type": GoalType.PERFORMANCE,
        "scope": "module",
        "categories": ["performance"],
        "criteria": ["対象処理が現在より高速化されている", "メモリ使用量が削減されている"],
    },
    {
        "keywords": ["リファクタリング", "refactor", "整理", "クリーン", "clean", "可読性"],
        "goal_type": GoalType.REFACTORING,
        "scope": "module",
        "categories": ["maintainability", "code_quality"],
        "criteria": ["コードが読みやすくなっている", "重複が排除されている"],
    },
    {
        "keywords": ["ドキュメント", "document", "docs", "README", "説明"],
        "goal_type": GoalType.DOCUMENTATION,
        "scope": "repository",
        "categories": ["documentation"],
        "criteria": ["主要APIが文書化されている", "README が最新状態になっている"],
    },
    {
        "keywords": [
            "移行",
            "migration",
            "アップグレード",
            "upgrade",
            "バージョン",
            "python",
            "framework",
        ],
        "goal_type": GoalType.MIGRATION,
        "scope": "repository",
        "categories": ["dependency_upgrade", "migration"],
        "criteria": ["移行後も既存テストがパスする", "依存バージョンが指定通り更新されている"],
    },
    {
        "keywords": ["自動化", "automation", "CI", "CD", "pipeline", "デプロイ", "deploy"],
        "goal_type": GoalType.AUTOMATION,
        "scope": "repository",
        "categories": ["automation", "devops"],
        "criteria": ["パイプラインが正常に動作する", "手動作業が削減されている"],
    },
    {
        "keywords": [
            "作りたい",
            "作成",
            "新しい",
            "new",
            "サービス",
            "service",
            "アプリ",
            "app",
            "API",
            "システム",
        ],
        "goal_type": GoalType.NEW_SERVICE,
        "scope": "repository",
        "categories": ["feature", "architecture"],
        "criteria": ["指定した機能が動作する", "E2Eテストがパスする"],
    },
    {
        "keywords": ["改善", "improve", "better", "向上", "enhance", "強化"],
        "goal_type": GoalType.IMPROVEMENT,
        "scope": "module",
        "categories": ["maintainability", "code_quality"],
        "criteria": ["改善前より品質スコアが向上している"],
    },
]

# スケール判定キーワード
_SCALE_LARGE = [
    "全体",
    "全面",
    "完全",
    "complete",
    "entire",
    "architecture",
    "アーキテクチャ",
    "リアーキ",
]
_SCALE_SMALL = ["ちょっと", "少し", "小さ", "minor", "simple", "単純", "1つ", "one"]

# ドメイン検出
_DOMAIN_RULES: List[Dict[str, Any]] = [
    {
        "keywords": ["ecommerce", "EC", "Eコマース", "ショッピング", "shopping", "cart", "カート"],
        "domain": "ecommerce",
    },
    {"keywords": ["api", "REST", "GraphQL", "endpoint"], "domain": "api"},
    {"keywords": ["cli", "コマンド", "command", "terminal"], "domain": "cli"},
    {"keywords": ["web", "フロント", "frontend", "html", "css"], "domain": "web"},
    {"keywords": ["database", "db", "SQL", "データベース"], "domain": "database"},
    {"keywords": ["AI", "ML", "machine learning", "機械学習", "LLM"], "domain": "ai_ml"},
]


# ────────────────────────────────────────────────────────────────── #
# GoalParser クラス                                                    #
# ────────────────────────────────────────────────────────────────── #


class GoalParser:
    """
    自然言語の目標テキストを StructuredGoal に変換するパーサー。

    LLM を使う場合（parse_with_llm）と
    ルールベース（parse_heuristic）の2モードを持つ。
    LLM なしでも実用的な品質で動作する。
    """

    def __init__(self, llm_client: Optional[Any] = None):
        self._llm = llm_client

    def parse(self, raw_text: str, use_llm: bool = False) -> StructuredGoal:
        """
        自然言語目標をパースして StructuredGoal を返す。

        Args:
            raw_text: 自然言語の目標テキスト
            use_llm: True の場合 LLM でより精緻な解析を行う

        Returns:
            StructuredGoal
        """
        if use_llm and self._llm:
            try:
                return self._parse_with_llm(raw_text)
            except Exception as e:
                logger.warning("LLM goal parsing failed, using heuristic: %s", e)

        return self._parse_heuristic(raw_text)

    # ------------------------------------------------------------------ #
    # ヒューリスティックパース                                              #
    # ------------------------------------------------------------------ #

    def _parse_heuristic(self, raw_text: str) -> StructuredGoal:
        """ルールベースでゴールを分類・構造化する。"""
        text_lower = raw_text.lower()

        # 1. 種別分類
        matched_rule = None
        max_matches = 0
        for rule in _CLASSIFICATION_RULES:
            matches = sum(1 for kw in rule["keywords"] if kw.lower() in text_lower)
            if matches > max_matches:
                max_matches = matches
                matched_rule = rule

        if not matched_rule:
            matched_rule = {
                "goal_type": GoalType.GENERAL,
                "scope": "repository",
                "categories": ["general"],
                "criteria": ["目標が達成されている"],
            }

        # 2. スケール判定
        scale = GoalScale.MEDIUM
        if any(kw.lower() in text_lower for kw in _SCALE_LARGE):
            scale = GoalScale.LARGE
        elif any(kw.lower() in text_lower for kw in _SCALE_SMALL):
            scale = GoalScale.SMALL

        # 3. ドメイン検出
        domain = ""
        for dr in _DOMAIN_RULES:
            if any(kw.lower() in text_lower for kw in dr["keywords"]):
                domain = dr["domain"]
                break

        # 4. 制約の推定
        constraints: List[str] = []
        if "互換" in raw_text or "backward" in text_lower or "既存" in raw_text:
            constraints.append("後方互換性を維持すること")
        if "テスト" in raw_text or "test" in text_lower:
            constraints.append("既存テストをすべてパスすること")
        if not constraints:
            constraints.append("既存機能を破壊しないこと")

        # 5. 目標の記述を生成
        description = self._generate_description(raw_text, matched_rule["goal_type"])

        # 6. 機能一覧の抽出（箇条書きや「〜機能」を検出）
        features = self._extract_features(raw_text)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return StructuredGoal(
            goal_id=f"goal:{matched_rule['goal_type']}:{ts}",
            raw_text=raw_text,
            goal_type=matched_rule["goal_type"],
            scope=matched_rule["scope"],
            description=description,
            success_criteria=matched_rule["criteria"],
            constraints=constraints,
            suggested_categories=matched_rule["categories"],
            scale=scale,
            domain=domain,
            features=features,
        )

    def _generate_description(self, raw_text: str, goal_type: str) -> str:
        """目標種別に応じた1行記述を生成する。"""
        type_prefix = {
            GoalType.SECURITY: "セキュリティを強化する",
            GoalType.TEST_COVERAGE: "テストカバレッジを向上させる",
            GoalType.PERFORMANCE: "パフォーマンスを改善する",
            GoalType.REFACTORING: "コードをリファクタリングする",
            GoalType.DOCUMENTATION: "ドキュメントを整備する",
            GoalType.MIGRATION: "依存関係・フレームワークを移行する",
            GoalType.AUTOMATION: "CI/CD・自動化を構築する",
            GoalType.NEW_SERVICE: "新しい機能・サービスを構築する",
            GoalType.IMPROVEMENT: "コードの品質・設計を改善する",
            GoalType.GENERAL: "目標を実現する",
        }
        prefix = type_prefix.get(goal_type, "目標を実現する")
        if len(raw_text) <= 50:
            return f"{raw_text}: {prefix}"
        return f"{prefix}（詳細: {raw_text[:60]}…）"

    def _extract_features(self, raw_text: str) -> List[str]:
        """テキストから機能リストを抽出する。"""
        features: List[str] = []
        # 「〜機能」パターン
        for match in re.finditer(r"[\w・/]+機能", raw_text):
            features.append(match.group())
        # 箇条書き（・ - * など）
        for line in raw_text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("・", "-", "*", "•")) and len(stripped) > 2:
                features.append(stripped[1:].strip())
        return list(dict.fromkeys(features))[:8]  # 重複除去 + 最大8件

    # ------------------------------------------------------------------ #
    # LLM パース                                                           #
    # ------------------------------------------------------------------ #

    def _parse_with_llm(self, raw_text: str) -> StructuredGoal:
        """LLM を使って高精度なゴールパースを行う。"""
        prompt = f"""以下の目標テキストを構造化してください。

目標テキスト: {raw_text}

以下のJSON形式で出力してください:
{{
  "goal_type": "new_service|improvement|security|performance|test_coverage|refactoring|documentation|migration|automation|general",
  "scope": "repository|module|function",
  "description": "1〜2文の明確な目標記述",
  "success_criteria": ["基準1", "基準2", "基準3"],
  "constraints": ["制約1", "制約2"],
  "scale": "small|medium|large",
  "domain": "ドメイン名または空文字",
  "features": ["機能1", "機能2"],
  "suggested_categories": ["カテゴリ1", "カテゴリ2"]
}}"""
        response = self._llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        json_match = re.search(r"\{.*?\}", content, re.DOTALL)
        if not json_match:
            logger.warning("LLM returned no JSON, falling back to heuristic")
            return self._parse_heuristic(raw_text)

        data = json.loads(json_match.group())
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return StructuredGoal(
            goal_id=f"goal:{data.get('goal_type', 'general')}:{ts}",
            raw_text=raw_text,
            goal_type=data.get("goal_type", GoalType.GENERAL),
            scope=data.get("scope", "repository"),
            description=data.get("description", raw_text),
            success_criteria=data.get("success_criteria", []),
            constraints=data.get("constraints", []),
            suggested_categories=data.get("suggested_categories", []),
            scale=data.get("scale", GoalScale.MEDIUM),
            domain=data.get("domain", ""),
            features=data.get("features", []),
        )
