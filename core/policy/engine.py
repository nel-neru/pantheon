"""
Pantheon - Approval Policy Engine

改善提案を「自動適用」か「人間承認待ち」かに仕分けするルールエンジン。
ルールは ~/.pantheon/policy.yaml に YAML で定義する。
人間起点・AI起点どちらも必ずこのエンジンを通る。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------- 判定結果 ----------


class ApprovalDecision(str, Enum):
    AUTO_APPROVE = "auto_approve"  # AIが自動適用してOK
    HUMAN_REQUIRED = "human_required"  # 人間の承認を待つ
    REJECT = "reject"  # 自動棄却


@dataclass
class PolicyVerdict:
    decision: ApprovalDecision
    reason: str
    rule_name: str = ""
    confidence: float = 1.0


@dataclass
class OrgBoundaryContext:
    """提案元 Organization の分離コンテキスト（汎用・特定ドメイン非依存）。

    PolicyEngine.evaluate に任意で渡し、外部目的 Organization（isolation_level=="external"）
    の提案が自ワークスペース外を変更しようとしていないかを境界チェックする。
    None を渡せば（デフォルト）境界チェックは一切作動せず、従来挙動と完全一致する。
    """

    isolation_level: str = "standard"
    allowed_path_scope: Optional[List[str]] = None


# ---------- デフォルトルール定義 ----------

DEFAULT_POLICY: Dict[str, Any] = {
    "version": "1.0",
    "auto_approve": {
        # この条件を全て満たす提案は自動適用
        "conditions": {
            "max_priority": "low",  # low優先度のみ
            "allowed_categories": [  # 許可カテゴリ
                "style",
                "documentation",
                "comment",
                "formatting",
            ],
            "forbidden_patterns": [  # ファイルパスに含まれてはいけない文字列
                "__init__.py",
                "pyproject.toml",
                "requirements",
                ".yaml",
                ".yml",
                ".env",
                "Dockerfile",
            ],
            "max_file_size_kb": 100,  # 対象ファイルが100KB以下
        }
    },
    "human_required": {
        # この条件のいずれかに該当したら人間承認必須
        "conditions": {
            "min_priority": "high",  # high優先度
            "categories": [  # 常に人間確認が必要なカテゴリ
                "security",
                "architecture",
                "database",
                "auth",
                "meta",
                "structural_intervention",  # 別 Organization への構造的介入（cross-org）
                "content_asset",  # ワークスペース資産（publishing 近接）は人間確認
                "external_action",  # 外部効果（投稿・課金・アカウント操作）は必ず人間確認（Phase 7 ゲート）
                "cross_org_handoff",  # ピア org 間の引き渡し（集客→販売→収益化）は承認ボタン
            ],
            "file_patterns": [  # 変更に慎重を要するファイル
                "main.py",
                "core/models",
                "core/platform",
                "tests/",
                "pyproject.toml",
            ],
        }
    },
    "auto_reject": {
        # この条件で自動棄却
        "conditions": {
            "empty_file_path": True,  # file_pathなし（meta提案）は棄却
            "disabled_categories": [],  # 明示的に無効化されたカテゴリ
        }
    },
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

    def evaluate(
        self,
        proposal: Dict[str, Any],
        *,
        org_context: OrgBoundaryContext | None = None,
    ) -> PolicyVerdict:
        """
        提案を評価して承認判定を返す。
        優先度: auto_reject > human_required > auto_approve > human_required(default)

        org_context（任意）: 提案元 Organization の分離コンテキスト。None（デフォルト）なら
        境界チェックは作動せず従来挙動と完全一致する。external 組織の提案が自ワークスペース外を
        触る場合のみ、構造介入/content_asset の専用判定の後に汎用境界ガードを適用する。
        """
        # 1. 自動棄却チェック
        verdict = self._check_auto_reject(proposal)
        if verdict:
            return verdict

        # 1.5 cross-org 構造介入チェック（別 Organization を変更する提案は必ず人間確認）
        verdict = self._check_intervention(proposal)
        if verdict:
            return verdict

        # 1.6 content_asset チェック（dispatch 述語と同じ 2-way。auto_approve に落とさない）
        verdict = self._check_content_asset(proposal)
        if verdict:
            return verdict

        # 1.65 cross-org 引き渡しチェック（ピア org 間の集客→販売→収益化の橋渡し）。
        # 別 org の作業キューに仕事を生むため、auto_approve には落とさず承認ボタンを要求する。
        verdict = self._check_handoff(proposal)
        if verdict:
            return verdict

        # 1.7 組織分離境界チェック（external 組織のワークスペース外脱出を防ぐ汎用ガード）。
        # 構造介入(1.5)・content_asset(1.6) の専用判定を先に通し、残った通常 code_file 提案にだけ適用する。
        verdict = self._check_org_boundary(proposal, org_context)
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

    def get_auto_approvable(self, proposals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """自動適用可能な提案のみ返す"""
        return [
            p
            for p, v in self.evaluate_batch(proposals)
            if v.decision == ApprovalDecision.AUTO_APPROVE
        ]

    def get_human_required(self, proposals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """人間承認が必要な提案のみ返す"""
        return [
            p
            for p, v in self.evaluate_batch(proposals)
            if v.decision == ApprovalDecision.HUMAN_REQUIRED
        ]

    # ---- 内部チェック ----

    def _check_auto_reject(self, p: Dict[str, Any]) -> Optional[PolicyVerdict]:
        cond = self._policy.get("auto_reject", {}).get("conditions", {})
        from core.models.organization import CROSS_ORG_HANDOFF_CATEGORY

        is_meta_or_intervention = bool(
            p.get("is_meta")
            or p.get("target_org_id")
            or p.get("target_org_name")
            or p.get("intervention_type")
            # ピア org 間の引き渡しもファイルを持たない設計 → empty_file_path で棄却しない。
            or p.get("category") == CROSS_ORG_HANDOFF_CATEGORY
        )
        # empty_file_path ルールは meta 提案／cross-org 構造介入／引き渡しを棄却してはいけない
        # （ファイルを持たない設計）。これらは後続（_check_intervention / _check_handoff /
        # human_required）へ委ねる。ただし disabled_categories（運用者の kill-switch）は
        # この carve-out の対象外で、介入であっても常に有効にする（auto_reject > human_required の優先順位を守る）。
        if cond.get("empty_file_path") and not p.get("file_path") and not is_meta_or_intervention:
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

    def _check_intervention(self, p: Dict[str, Any]) -> Optional[PolicyVerdict]:
        """別 Organization の構造を変更する cross-org 介入は必ず人間確認にする。

        対象 org のモデルを直接変更しうるため、auto_approve には決して落とさない（安全側）。
        category / intervention_type / target_org_* のいずれかがあれば介入とみなす。
        """
        is_intervention = (
            p.get("category") == "structural_intervention"
            or p.get("intervention_type")
            or p.get("target_org_id")
            or p.get("target_org_name")
        )
        if is_intervention:
            return PolicyVerdict(
                decision=ApprovalDecision.HUMAN_REQUIRED,
                reason="別 Organization を変更する構造的介入は人間確認必須",
                rule_name="intervention.cross_org",
            )
        return None

    def _check_content_asset(self, p: Dict[str, Any]) -> Optional[PolicyVerdict]:
        """content_asset（ワークスペース資産）提案は必ず人間確認にする。

        承認/適用ディスパッチ（is_content_asset_dict）は category または target_kind の
        どちらでも content_asset 判定する。ポリシーがそれより狭い（category だけ）と、
        target_kind のみの提案が auto_approve をすり抜けるため、同じ述語に揃える。
        """
        from core.models.organization import is_content_asset_dict

        if is_content_asset_dict(p):
            return PolicyVerdict(
                decision=ApprovalDecision.HUMAN_REQUIRED,
                reason="content_asset（ワークスペース資産・publishing 近接）は人間確認必須",
                rule_name="human_required.content_asset",
            )
        return None

    def _check_handoff(self, p: Dict[str, Any]) -> Optional[PolicyVerdict]:
        """ピア Organization 間の引き渡し（cross_org_handoff）は必ず人間確認にする。

        SNS 集客 → note 販売 → アフィリ収益化 のように、ある org の成果物が別 org の
        作業（有料コンテンツ生成・収益化導線）を起動する。承認ボタン＝この人間ゲート。
        auto_approve には決して落とさない（構造介入・content_asset と同じ安全側の扱い）。
        """
        from core.models.organization import CROSS_ORG_HANDOFF_CATEGORY

        if (p.get("category") or "") == CROSS_ORG_HANDOFF_CATEGORY:
            return PolicyVerdict(
                decision=ApprovalDecision.HUMAN_REQUIRED,
                reason="ピア org 間の引き渡し（集客→販売→収益化）は人間確認必須",
                rule_name="human_required.cross_org_handoff",
            )
        return None

    @staticmethod
    def _path_segments(file_path: str) -> List[str]:
        """OS 区切りを正規化してパスをセグメント分割する（Windows の `\\` も `/` も扱う）。"""
        return [seg for seg in file_path.replace("\\", "/").split("/") if seg]

    def _check_org_boundary(
        self, p: Dict[str, Any], ctx: Optional[OrgBoundaryContext]
    ) -> Optional[PolicyVerdict]:
        """external 組織の提案が自ワークスペース外を変更しようとしていないかを汎用的に検査する。

        ctx が None、または external 以外（core/standard）なら完全に no-op（従来挙動）。
        特定ドメイン（アフィリエイト等）の知識は一切持たず、純粋にパススコープのみで判定する。
        """
        if ctx is None or ctx.isolation_level != "external":
            return None

        file_path = str(p.get("file_path") or "")
        # 空 file_path（構造介入/meta）は上流で処理済み。境界ガードは作動しない。
        if not file_path:
            return None

        normalized = file_path.replace("\\", "/")
        segments = self._path_segments(file_path)

        # 1) 絶対パス または `..` セグメント = ワークスペース外への脱出 → 強い境界（REJECT）。
        if os.path.isabs(file_path) or ".." in segments:
            return PolicyVerdict(
                decision=ApprovalDecision.REJECT,
                reason="external 組織は自ワークスペース外（絶対パス/親ディレクトリ）を変更できません",
                rule_name="org_boundary.escape",
            )

        # 2) allowed_path_scope が宣言されていれば、その接頭辞配下のみ許可（セグメント境界一致）。
        scope = ctx.allowed_path_scope or []
        if scope:
            in_scope = any(
                normalized == prefix.replace("\\", "/").rstrip("/")
                or normalized.startswith(prefix.replace("\\", "/").rstrip("/") + "/")
                for prefix in scope
                if prefix
            )
            if not in_scope:
                return PolicyVerdict(
                    decision=ApprovalDecision.HUMAN_REQUIRED,
                    reason="external 組織の宣言スコープ（allowed_path_scope）外への変更は人間確認必須",
                    rule_name="org_boundary.out_of_scope",
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
            path = str(
                changed_file.get("file_path")
                or changed_file.get("path")
                or file_path
                or "<unknown>"
            )
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
