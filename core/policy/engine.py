"""
Pantheon - Approval Policy Engine

改善提案を「自動適用」か「人間承認待ち」かに仕分けするルールエンジン。
ルールは ~/.pantheon/policy.yaml に YAML で定義する。
人間起点・AI起点どちらも必ずこのエンジンを通る。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------- 判定結果 ----------

class ApprovalDecision(str, Enum):
    AUTO_APPROVE = "auto_approve"   # AIが自動適用してOK
    HUMAN_REQUIRED = "human_required"  # 人間の承認を待つ
    REJECT = "reject"               # 自動棄却


@dataclass
class PolicyVerdict:
    decision: ApprovalDecision
    reason: str
    rule_name: str = ""
    confidence: float = 1.0


# ---------- デフォルトルール定義 ----------

DEFAULT_POLICY: Dict[str, Any] = {
    "version": "1.0",
    "auto_approve": {
        # この条件を全て満たす提案は自動適用
        "conditions": {
            "max_priority": "low",           # low優先度のみ
            "allowed_categories": [          # 許可カテゴリ
                "style", "documentation", "comment", "formatting",
            ],
            "forbidden_patterns": [          # ファイルパスに含まれてはいけない文字列
                "__init__.py", "pyproject.toml", "requirements",
                ".yaml", ".yml", ".env", "Dockerfile",
            ],
            "max_file_size_kb": 100,         # 対象ファイルが100KB以下
        }
    },
    "human_required": {
        # この条件のいずれかに該当したら人間承認必須
        "conditions": {
            "min_priority": "high",          # high優先度
            "categories": [                  # 常に人間確認が必要なカテゴリ
                "security", "architecture", "database", "auth",
            ],
            "file_patterns": [               # 変更に慎重を要するファイル
                "main.py", "core/models", "core/platform",
                "tests/", "pyproject.toml",
            ],
        }
    },
    "auto_reject": {
        # この条件で自動棄却
        "conditions": {
            "empty_file_path": True,         # file_pathなし（meta提案）は棄却
            "disabled_categories": [],       # 明示的に無効化されたカテゴリ
        }
    }
}


# ---------- エンジン本体 ----------

class PolicyEngine:
    """
    改善提案の承認ルーティングを決定する。
    全フロー（ユーザー起点・AI起点）が共通して経由する判定層。
    """

    def __init__(self, policy_path: Optional[Path] = None):
        self._policy_path = policy_path
        self._policy = self._load_policy()

    def _load_policy(self) -> Dict[str, Any]:
        if self._policy_path and self._policy_path.exists():
            try:
                import yaml
                with open(self._policy_path, encoding="utf-8") as f:
                    loaded = yaml.safe_load(f)
                    if loaded:
                        logger.info("Policy loaded from %s", self._policy_path)
                        return loaded
            except Exception as e:
                logger.warning("Failed to load policy file: %s — using defaults", e)
        return DEFAULT_POLICY

    def evaluate(self, proposal: Dict[str, Any]) -> PolicyVerdict:
        """
        提案を評価して承認判定を返す。
        優先度: auto_reject > human_required > auto_approve > human_required(default)
        """
        # 1. 自動棄却チェック
        verdict = self._check_auto_reject(proposal)
        if verdict:
            return verdict

        # 2. 人間必須チェック（high risk）
        verdict = self._check_human_required(proposal)
        if verdict:
            return verdict

        # 3. 自動承認チェック（low risk 条件をすべて満たす）
        verdict = self._check_auto_approve(proposal)
        if verdict:
            return verdict

        # 4. デフォルト: 人間確認
        return PolicyVerdict(
            decision=ApprovalDecision.HUMAN_REQUIRED,
            reason="デフォルトポリシー: ルールに合致しないため人間確認",
            rule_name="default",
        )

    def evaluate_batch(
        self, proposals: List[Dict[str, Any]]
    ) -> List[tuple[Dict[str, Any], PolicyVerdict]]:
        """複数提案をまとめて評価する"""
        return [(p, self.evaluate(p)) for p in proposals]

    def get_auto_approvable(
        self, proposals: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """自動適用可能な提案のみ返す"""
        return [
            p for p, v in self.evaluate_batch(proposals)
            if v.decision == ApprovalDecision.AUTO_APPROVE
        ]

    def get_human_required(
        self, proposals: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """人間承認が必要な提案のみ返す"""
        return [
            p for p, v in self.evaluate_batch(proposals)
            if v.decision == ApprovalDecision.HUMAN_REQUIRED
        ]

    # ---- 内部チェック ----

    def _check_auto_reject(self, p: Dict[str, Any]) -> Optional[PolicyVerdict]:
        cond = self._policy.get("auto_reject", {}).get("conditions", {})
        if cond.get("empty_file_path") and not p.get("file_path"):
            return PolicyVerdict(
                decision=ApprovalDecision.REJECT,
                reason="file_path が空のため自動棄却（meta-level 提案）",
                rule_name="auto_reject.empty_file_path",
            )

        disabled_categories = set(cond.get("disabled_categories", []))
        if p.get("category") in disabled_categories:
            return PolicyVerdict(
                decision=ApprovalDecision.REJECT,
                reason=f"カテゴリ '{p.get('category')}' は無効化されているため自動棄却",
                rule_name="auto_reject.disabled_categories",
            )
        return None

    def _check_human_required(self, p: Dict[str, Any]) -> Optional[PolicyVerdict]:
        cond = self._policy.get("human_required", {}).get("conditions", {})

        # 優先度チェック
        min_priority = cond.get("min_priority", "high")
        priority_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        if priority_order.get(p.get("priority", "low"), 0) >= priority_order.get(min_priority, 2):
            return PolicyVerdict(
                decision=ApprovalDecision.HUMAN_REQUIRED,
                reason=f"優先度 '{p.get('priority')}' は人間確認必須",
                rule_name="human_required.min_priority",
            )

        # カテゴリチェック
        for cat in cond.get("categories", []):
            if cat == (p.get("category") or ""):
                return PolicyVerdict(
                    decision=ApprovalDecision.HUMAN_REQUIRED,
                    reason=f"カテゴリ '{cat}' は常に人間確認",
                    rule_name="human_required.categories",
                )

        # ファイルパスチェック
        file_path = p.get("file_path", "")
        for pattern in cond.get("file_patterns", []):
            if pattern in file_path:
                return PolicyVerdict(
                    decision=ApprovalDecision.HUMAN_REQUIRED,
                    reason=f"ファイル '{file_path}' は変更に慎重を要する",
                    rule_name="human_required.file_patterns",
                )
        return None

    def _collect_changed_file_sizes_kb(self, proposal: Dict[str, Any]) -> List[tuple[str, float]]:
        sizes: List[tuple[str, float]] = []

        def append_size(path: str, raw_value: Any, *, divide_by_1024: bool = False) -> None:
            if raw_value in (None, ""):
                return
            try:
                size = float(raw_value)
            except (TypeError, ValueError):
                return
            if divide_by_1024:
                size /= 1024
            sizes.append((path, size))

        file_path = str(proposal.get("file_path") or "")
        append_size(file_path, proposal.get("file_size_kb"))
        append_size(file_path, proposal.get("size_kb"))
        append_size(file_path, proposal.get("size_bytes"), divide_by_1024=True)

        for changed_file in proposal.get("changed_files", []):
            if not isinstance(changed_file, dict):
                continue
            path = str(changed_file.get("file_path") or changed_file.get("path") or file_path or "<unknown>")
            append_size(path, changed_file.get("file_size_kb"))
            append_size(path, changed_file.get("size_kb"))
            append_size(path, changed_file.get("size_bytes"), divide_by_1024=True)

        return sizes

    def _check_auto_approve(self, p: Dict[str, Any]) -> Optional[PolicyVerdict]:
        cond = self._policy.get("auto_approve", {}).get("conditions", {})
        priority_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}

        # 優先度上限
        max_p = cond.get("max_priority", "low")
        if priority_order.get(p.get("priority", "medium"), 1) > priority_order.get(max_p, 0):
            return None  # 条件不満足 → 次のルールへ

        # カテゴリ許可リスト
        allowed = cond.get("allowed_categories", [])
        if allowed and (p.get("category") or "") not in allowed:
            return None

        # 禁止パターンチェック
        file_path = p.get("file_path", "")
        for pattern in cond.get("forbidden_patterns", []):
            if pattern in file_path:
                return None

        max_file_size_kb = cond.get("max_file_size_kb")
        if max_file_size_kb is not None:
            for changed_path, size_kb in self._collect_changed_file_sizes_kb(p):
                if size_kb > float(max_file_size_kb):
                    logger.info(
                        "Auto-approve skipped for %s because %.1fKB exceeds max_file_size_kb=%s",
                        changed_path,
                        size_kb,
                        max_file_size_kb,
                    )
                    return None

        return PolicyVerdict(
            decision=ApprovalDecision.AUTO_APPROVE,
            reason="全ての自動承認条件を満たしています",
            rule_name="auto_approve",
            confidence=0.9,
        )

    def save_default_policy(self, path: Path) -> None:
        """デフォルトポリシーを YAML ファイルとして保存する"""
        import yaml
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(DEFAULT_POLICY, f, allow_unicode=True, default_flow_style=False)
        logger.info("Default policy saved to %s", path)
