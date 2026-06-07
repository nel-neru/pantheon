"""
Pantheon - Core Data Models (New Terminology)

「会社」比喩を完全に撤廃し、以下のように再定義：
- Organization: 目的を持った自律的な組織
- Division: 組織内の機能別グループ
- Team: Division内の実行単位
- SpecialistAgent: 2〜3スキルを保有する専門エージェント
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

# ============================================================
# Quality Review Models
# ============================================================


class QualityDimension(str, Enum):
    THINKING_QUALITY = "thinking_quality"
    EXECUTION_QUALITY = "execution_quality"
    OUTPUT_QUALITY = "output_quality"
    COST_EFFICIENCY = "cost_efficiency"
    LEARNING_EFFICIENCY = "learning_efficiency"
    REUSABILITY = "reusability"


class QualityScore(BaseModel):
    dimension: str
    score: float = Field(..., ge=1, le=10)
    comment: str = ""
    evidence: str = ""


class QualityReview(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    overall_score: float = Field(..., ge=1, le=10)
    dimension_scores: List[QualityScore] = Field(default_factory=list)
    critical_findings: List[str] = Field(default_factory=list)
    improvement_opportunities: List[str] = Field(default_factory=list)
    consultant_comment: str = ""
    target_type: str = "general_task"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StructuralInterventionType(str, Enum):
    """HQ（Meta-Improvement Organization）が別 Organization に対して行う構造的介入の種別。"""

    ADD_DIVISION = "add_division"
    ADD_TEAM = "add_team"
    ADD_AGENT = "add_agent"
    INJECT_SKILLS = "inject_skills"
    SET_GOAL = "set_goal"


# 構造的介入提案を識別する category。PolicyEngine と適用ディスパッチが参照する。
STRUCTURAL_INTERVENTION_CATEGORY = "structural_intervention"
STRUCTURAL_INTERVENTION_TYPES = tuple(t.value for t in StructuralInterventionType)


def is_structural_intervention_dict(data: dict) -> bool:
    """dict 形式の提案が cross-org 構造介入かどうかを判定する単一の真実源。

    モデル（``ImprovementProposal.is_structural_intervention``）・PolicyEngine・
    承認/適用ディスパッチ（CLI/Web）はすべてこの 4-way 判定に揃える
    （ディスパッチが policy より狭いと、policy が介入と認めた提案を取りこぼす）。
    """
    return bool(
        data.get("category") == STRUCTURAL_INTERVENTION_CATEGORY
        or data.get("intervention_type")
        or data.get("target_org_id")
        or data.get("target_org_name")
    )


# 非コード資産（記事/コピー/スクリプト等）をワークスペース内に安全適用する提案（Phase 6/7）。
CONTENT_ASSET_CATEGORY = "content_asset"
CONTENT_ASSET_TARGET_KIND = "content_asset"


def is_content_asset_dict(data: dict) -> bool:
    """dict 形式の提案が「ワークスペース内資産」提案かどうか（適用ディスパッチで共通利用）。

    収益 Organization 等のコンテンツ/スクリプトを target_repo ワークスペース内に
    安全に生成/更新する提案。コードファイル改善（LLM 書換）とは別経路で適用する。
    """
    return bool(
        data.get("category") == CONTENT_ASSET_CATEGORY
        or data.get("target_kind") == CONTENT_ASSET_TARGET_KIND
    )


class ImprovementProposal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    review_id: UUID
    priority: str = "medium"  # "high" | "medium" | "low"
    category: str = "general"
    title: str
    description: str
    file_path: str = ""  # 対象ファイルパス（空の場合は approve 不可）
    expected_impact: str = ""
    implementation_difficulty: str = "medium"
    status: str = "proposed"  # "proposed" | "pending" | "in_progress" | "done" | "rejected" | "failed" | "cancelled"
    is_meta: bool = Field(
        False, description="Atlas/システムレベルの meta 提案（空 file_path をポリシーが許容しうる）"
    )
    dedupe_key: str = Field(
        "", description="再生成をまたいで同一性を保つ安定ハッシュ（重複排除用）"
    )
    # ---- Phase 5: HQ → 子 Organization への構造的介入（cross-org）----
    # すべて Optional + デフォルト付き。既存の永続化済み JSON を model_validate_json で
    # 読み戻せるよう、後方互換（additive）を厳守する。
    target_org_id: str | None = Field(
        None, description="介入対象 Organization の id（cross-org 構造介入用）"
    )
    target_org_name: str | None = Field(
        None, description="介入対象 Organization の名前（id 解決のフォールバック）"
    )
    source_org_name: str | None = Field(
        None, description="提案元 Organization（HQ/Meta 等）— 監査・来歴用"
    )
    intervention_type: str | None = Field(
        None,
        description="構造介入の種別（add_division / add_team / add_agent / inject_skills / set_goal）",
    )
    target_kind: str | None = Field(
        None, description="介入対象の種類（org_structure / code_file / content_asset 等）"
    )
    target_ref: str | None = Field(
        None, description="介入対象の柔軟な識別子（Division 名・Team 名・skill set 等）"
    )
    intervention_spec: Optional[Dict] = Field(
        None, description="構造介入のペイロード（division/team/agent/skill/goal の仕様）"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_structural_intervention(self) -> bool:
        """この提案が cross-org 構造介入かどうか（適用経路の分岐に使う）。"""
        return is_structural_intervention_dict(
            {
                "category": self.category,
                "intervention_type": self.intervention_type,
                "target_org_id": self.target_org_id,
                "target_org_name": self.target_org_name,
            }
        )


ACTIVE_IMPROVEMENT_PROPOSAL_STATUSES = ("proposed", "pending", "in_progress")
TERMINAL_IMPROVEMENT_PROPOSAL_STATUSES = ("done", "rejected", "failed", "cancelled")


def is_active_improvement_proposal_status(status: str | None) -> bool:
    return (status or "proposed") in ACTIVE_IMPROVEMENT_PROPOSAL_STATUSES


# ============================================================
# Organization Status / Types
# ============================================================


class OrganizationStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"
    INCUBATING = "incubating"


class DivisionType(str, Enum):
    # Meta-Improvement Organization向け
    ORG_EVOLUTION = "org_evolution"
    AGENT_ARCHITECTURE = "agent_architecture"
    TOOL_INTEGRATION = "tool_integration"
    QUALITY_ASSURANCE = "quality_assurance"
    PERFORMANCE_OPTIMIZATION = "performance_optimization"
    KNOWLEDGE_MANAGEMENT = "knowledge_management"
    # 収益（非SE）Organization向け（Phase 6）
    CONTENT_PRODUCTION = "content_production"
    AUDIENCE_DEVELOPMENT = "audience_development"
    MONETIZATION = "monetization"


class AgentSkill(str, Enum):
    STRATEGIC_PLANNING = "strategic_planning"
    CORPORATE_RESEARCH = "corporate_research"
    ORG_DESIGN = "org_design"
    AGENT_WORKFLOW_DESIGN = "agent_workflow_design"
    PROMPT_ENGINEERING = "prompt_engineering"
    TOOL_INTEGRATION = "tool_integration"
    DEEP_RESEARCH = "deep_research"
    PERFORMANCE_ANALYSIS = "performance_analysis"
    KNOWLEDGE_CURATION = "knowledge_curation"
    CODEBASE_EXPLORATION = "codebase_exploration"
    # 収益ドメイン（Phase 6）
    CONTENT_STRATEGY = "content_strategy"
    AUDIENCE_GROWTH = "audience_growth"
    PERFORMANCE_MARKETING = "performance_marketing"


class SpecialistAgent(BaseModel):
    """2〜3個の専門スキルを抱えたSpecialist Agent"""

    id: UUID = Field(default_factory=uuid4)
    name: str
    skills: List[AgentSkill] = Field(..., min_length=2, max_length=3)
    description: str = ""
    current_task: Optional[str] = None
    performance_score: float = Field(50.0, ge=0, le=100)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def has_skill(self, skill: AgentSkill) -> bool:
        return skill in self.skills

    def add_skill(self, skill: AgentSkill) -> None:
        if skill not in self.skills and len(self.skills) < 3:
            self.skills.append(skill)


class Team(BaseModel):
    """Team（Division内の実行単位）"""

    id: UUID = Field(default_factory=uuid4)
    name: str
    division_type: DivisionType
    agents: List[SpecialistAgent] = Field(default_factory=list)
    mission: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Division(BaseModel):
    """Division（組織内の機能別グループ）"""

    id: UUID = Field(default_factory=uuid4)
    name: str
    type: DivisionType
    teams: List[Team] = Field(default_factory=list)
    mission: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def add_team(self, team: Team) -> None:
        self.teams.append(team)


class Organization(BaseModel):
    """Organization（目的を持った自律的な組織 / 子会社）"""

    id: UUID = Field(default_factory=uuid4)
    name: str
    purpose: str  # この組織が達成したい目的
    target_repo_path: str | None = None  # 担当するリポジトリの絶対パス
    github_repo: str | None = Field(
        None, description="GitHub リポジトリ (owner/repo) — 改善提案の PR 作成に使用"
    )
    divisions: List[Division] = Field(default_factory=list)
    status: OrganizationStatus = OrganizationStatus.INCUBATING
    autonomy_score: float = Field(40.0, ge=0, le=100)
    improvement_velocity: float = Field(50.0, ge=0, le=100)
    is_system: bool = Field(False, description="システム組織（削除不可）")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    icon_data: str = Field("", description="カスタムアイコン（base64 data URLまたはSVG文字列）")

    @field_validator("target_repo_path")
    @classmethod
    def validate_target_repo_path(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return value
        if not Path(value).is_absolute():
            raise ValueError("target_repo_path must be an absolute path")
        return value

    def add_division(self, division: Division) -> None:
        self.divisions.append(division)

    def get_all_agents(self) -> List[SpecialistAgent]:
        agents = []
        for division in self.divisions:
            for team in division.teams:
                agents.extend(team.agents)
        return agents


class OrganizationMetrics(BaseModel):
    """個別Organizationの成長指標"""

    organization_id: str
    name: str
    autonomy_score: float
    improvement_velocity: float
    avg_review_score: float
    pending_proposals_count: int
    health_score: float
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GroupHQState(BaseModel):
    """Core（中核）の状態"""

    version: str = "0.3.0-reorg"
    organizations: Dict[UUID, Organization] = Field(default_factory=dict)
    total_agents: int = 0
    group_health_score: float = 50.0
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def add_organization(self, org: Organization) -> None:
        self.organizations[org.id] = org
        self._recalculate()

    def _recalculate(self) -> None:
        self.total_agents = sum(len(org.get_all_agents()) for org in self.organizations.values())
        if self.organizations:
            self.group_health_score = sum(
                org.autonomy_score for org in self.organizations.values()
            ) / len(self.organizations)
        self.last_updated = datetime.now(timezone.utc)
