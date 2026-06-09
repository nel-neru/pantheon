"""
OrgInstantiator — 目標に最適な Organization を自動構築 (M-03)

GoalParser → GoalDecomposer → OrgInstantiator のパイプラインで
自然言語の目標から Organization を自動作成する。

OrganizationDesigner (E-01) を使って一貫した設計を行い、
既存 Organization が利用可能な場合は流用する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List, Optional

from core.goals.goal_parser import GoalType, StructuredGoal
from core.models.organization import Organization

logger = logging.getLogger(__name__)


@dataclass
class InstantiationResult:
    """Organization 作成の結果。"""

    organization: Organization
    is_new: bool  # True: 新規作成、False: 既存を流用
    template_used: str = ""
    reason: str = ""


class OrgInstantiator:
    """
    StructuredGoal から最適な Organization を構築するクラス。

    - 目標ドメイン・種別に応じた OrganizationDesigner テンプレートを選択
    - 既存 Organization が目的と一致する場合は流用
    - Platform State への保存は呼び出し元が担当
    """

    # GoalType → テンプレート名のマッピング
    GOAL_TYPE_TO_TEMPLATE: dict = {
        GoalType.SECURITY: "security_org",
        GoalType.TEST_COVERAGE: "quality_assurance_org",
        GoalType.PERFORMANCE: "performance_org",
        GoalType.REFACTORING: "code_quality_org",
        GoalType.DOCUMENTATION: "knowledge_org",
        GoalType.NEW_SERVICE: "development_org",
        GoalType.IMPROVEMENT: "improvement_org",
        GoalType.AUTOMATION: "automation_org",
        GoalType.MIGRATION: "migration_org",
        GoalType.GENERAL: "general_org",
    }

    def __init__(
        self,
        org_designer: Optional[Any] = None,  # OrganizationDesigner instance
        existing_orgs: Optional[List[Organization]] = None,
    ):
        from core.hierarchy.org_designer import OrganizationDesigner

        self._designer = org_designer or OrganizationDesigner()
        self._existing_orgs = existing_orgs or []

    def set_existing_orgs(self, orgs: List[Organization]) -> None:
        """流用判定に使う既存 Organization 一覧を差し替える。

        パイプラインが実行のたびに最新の永続化済み Organization を渡し、同一プロセスで
        連続実行しても同名 Organization が増殖しないようにするためのフック。
        """
        self._existing_orgs = list(orgs or [])

    def instantiate(self, goal: StructuredGoal) -> InstantiationResult:
        """
        StructuredGoal に最適な Organization を返す。
        既存 Organization が目的に合う場合は流用、なければ新規作成。
        """
        # 1. 既存 Org に流用できるものがあるか確認
        reuse = self._find_reusable_org(goal)
        if reuse:
            logger.info("Reusing existing organization: %s", reuse.name)
            return InstantiationResult(
                organization=reuse,
                is_new=False,
                reason=f"既存 Organization '{reuse.name}' が目標と一致するため流用",
            )

        # 2. 新規作成（ただし同名の既存 Org があれば流用して名前重複を防ぐ）
        org_name = self._generate_org_name(goal)
        same_name = self._find_org_by_name(org_name)
        if same_name is not None:
            logger.info("Reusing organization by name to avoid duplicate: %s", org_name)
            return InstantiationResult(
                organization=same_name,
                is_new=False,
                reason=f"同名 Organization '{org_name}' が既に存在するため流用（重複作成を防止）",
            )

        spec = self._designer.design(goal.description, org_name=org_name)
        org = self._designer.instantiate(spec)
        org.purpose = goal.description

        return InstantiationResult(
            organization=org,
            is_new=True,
            template_used=spec.template_name or goal.goal_type,
            reason=f"目標 '{goal.goal_type}' に対して新規 Organization を設計・作成",
        )

    def _find_reusable_org(self, goal: StructuredGoal) -> Optional[Organization]:
        """既存 Organization の中から目標と最も一致するものを探す。"""
        if not self._existing_orgs:
            return None

        for org in self._existing_orgs:
            purpose_lower = org.purpose.lower()
            goal_keywords = [
                goal.goal_type.replace("_", " "),
                goal.domain,
            ] + (goal.suggested_categories or [])

            matches = sum(1 for kw in goal_keywords if kw and kw.lower() in purpose_lower)
            if matches >= 1:
                return org
        return None

    def _find_org_by_name(self, name: str) -> Optional[Organization]:
        """既存 Organization から完全同名のものを返す（重複作成の最終ガード）。"""
        target = (name or "").strip().lower()
        if not target:
            return None
        for org in self._existing_orgs:
            if org.name.strip().lower() == target:
                return org
        return None

    def _generate_org_name(self, goal: StructuredGoal) -> str:
        """目標から Organization 名を生成する。"""
        type_names = {
            GoalType.SECURITY: "Security Organization",
            GoalType.TEST_COVERAGE: "QA Organization",
            GoalType.PERFORMANCE: "Performance Organization",
            GoalType.REFACTORING: "Code Quality Organization",
            GoalType.DOCUMENTATION: "Knowledge Organization",
            GoalType.NEW_SERVICE: "Development Organization",
            GoalType.IMPROVEMENT: "Improvement Organization",
            GoalType.AUTOMATION: "Automation Organization",
            GoalType.MIGRATION: "Migration Organization",
            GoalType.GENERAL: "General Organization",
        }
        base = type_names.get(goal.goal_type, "General Organization")
        if goal.domain:
            return f"{goal.domain.title()} {base}"
        return base
