"""
HQ Intervention Proposer — 本社（Meta-Improvement Organization）が子 Organization を
診断し、構造的介入提案を生成する（Phase 5）。

「HQ が子会社を強化する」を既存機械（OrgSelfDiagnostics + ImprovementProposal +
PolicyEngine + 構造介入 executor）の *一般化* で実現する。LLM なしの決定論的ヒューリ
スティックで弱みを介入に写像するため、テストしやすく安全。

フロー:
  1. 子 Organization を列挙（system / Meta は除外）
  2. 各 org のメトリクス（自律スコア・採択/却下数・知識数）から OrgSelfDiagnostics で診断
  3. 弱みごとに構造介入 ``ImprovementProposal`` を組み立て（安定 dedupe_key 付き）
  4. 対象 org の .pantheon/improvements に保存（来歴 source_org_name=HQ 付き）
     → 通常の approve/apply（PolicyEngine + PreTask 経由）で人間が承認して適用する。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from core.hierarchy.org_diagnostics import DiagnosticReport, OrgSelfDiagnostics
from core.models.organization import (
    STRUCTURAL_INTERVENTION_CATEGORY,
    DivisionType,
    ImprovementProposal,
    Organization,
    StructuralInterventionType,
)
from core.orchestration.structural_intervention import build_intervention_proposal

if TYPE_CHECKING:
    from core.platform.state import PlatformStateManager
    from core.state.manager import RepoStateManager

# 弱み文字列（OrgSelfDiagnostics が出す定型句）→ 構造介入の写像キー。
_WEAKNESS_LOW_AUTONOMY = "自律スコアの改善が必要"
_WEAKNESS_LOW_QUALITY = "提案の質向上が必要"
_WEAKNESS_LOW_KNOWLEDGE = "知識蓄積の強化が必要"


def _plugin_department_to_division_spec(department: Dict[str, Any]) -> Dict[str, Any]:
    """事業部プラグインの department 定義（teams[].required_skills）を ADD_DIVISION の
    spec 形式（teams[].agents[].skills）へ変換する。

    プラグインカタログ（org_factory/テンプレと同形）と構造介入 executor
    （structural_intervention._build_team は agents を読む）の橋渡し。各チームの
    required_skills を 1 体の Specialist のスキルに写像する（2〜3 正規化は executor が担う）。
    """
    teams_out: List[Dict[str, Any]] = []
    for team in department.get("teams", []) or []:
        if not isinstance(team, dict):
            continue
        team_name = str(team.get("name") or "New Team")
        mission = str(team.get("mission") or "")
        teams_out.append(
            {
                "name": team_name,
                "mission": mission,
                "agents": [
                    {
                        "name": f"{team_name} Specialist",
                        "skills": list(team.get("required_skills") or []),
                        "description": mission,
                    }
                ],
            }
        )
    return {
        "name": department.get("name"),
        "type": department.get("type"),
        "mission": department.get("mission", ""),
        "teams": teams_out,
    }


class HQInterventionProposer:
    """本社が子 Organization を診断し、構造的介入提案を生成・永続化する。"""

    def __init__(
        self,
        psm: Optional["PlatformStateManager"] = None,
        *,
        source_org_name: Optional[str] = None,
    ):
        if psm is None:
            from core.platform.state import PlatformStateManager

            psm = PlatformStateManager()
        self._psm = psm
        self._diag = OrgSelfDiagnostics()
        if source_org_name is None:
            try:
                from core.bootstrap import META_ORG_NAME

                source_org_name = META_ORG_NAME
            except Exception:  # noqa: BLE001 - bootstrap 不在でも proposer は動く
                source_org_name = "Meta-Improvement Organization"
        self._source = source_org_name

    # ------------------------------------------------------------------ #
    # 列挙・診断                                                          #
    # ------------------------------------------------------------------ #

    def list_target_orgs(self) -> List[Organization]:
        """介入対象になりうる子 Organization（system / HQ 自身は除外）。"""
        return [
            org
            for org in self._psm.load_organizations()
            if not org.is_system and org.name != self._source
        ]

    def diagnose_org(self, org: Organization) -> DiagnosticReport:
        sm = self._psm.get_org_state_manager(org)
        accepted, rejected = self._proposal_counts(sm)
        knowledge = self._knowledge_count(sm)
        return self._diag.diagnose(
            org_name=org.name,
            health_score=org.autonomy_score,
            accepted_count=accepted,
            rejected_count=rejected,
            knowledge_count=knowledge,
        )

    # ------------------------------------------------------------------ #
    # 提案生成                                                            #
    # ------------------------------------------------------------------ #

    def propose_for_org(self, org: Organization) -> List[ImprovementProposal]:
        """1 つの org に対する構造介入提案リストを返す（永続化しない）。"""
        report = self.diagnose_org(org)
        proposals: List[ImprovementProposal] = []
        for weakness in report.weaknesses:
            built = self._intervention_for_weakness(org, weakness, report)
            if built is not None:
                proposals.append(built)
        # Phase 8: 実成果（OutcomeStore）を第一級シグナルとして介入に反映する。
        outcome_proposal = self._intervention_from_outcomes(org)
        if outcome_proposal is not None:
            proposals.append(outcome_proposal)
        # Phase 1: 「リーチ有・収益0」の org に *具体的な収益化事業部* の新設を提案する
        #          （目標設定＝why に対し、事業部プラグイン追加＝how。自己拡大の出口）。
        monetization_proposal = self._intervention_add_monetization_division(org)
        if monetization_proposal is not None:
            proposals.append(monetization_proposal)
        return proposals

    def _intervention_add_monetization_division(
        self, org: Organization
    ) -> Optional[ImprovementProposal]:
        """成果ベースの *構造* 介入: 収益化事業部が未設置の収益0 org に追加を提案する。

        ``_intervention_from_outcomes`` の SET_GOAL（目標化）を補完する具体策。事業部
        プラグイン（``core.orchestration.division_plugins``）の department 定義を ADD_DIVISION
        の spec に変換して提案する（承認→構造介入 executor で適用）。
        """
        from core.metrics.outcomes import OutcomeStore
        from core.orchestration.division_plugins import get_division_plugin

        summary = OutcomeStore(platform_home=self._psm.platform_home).summary_for_org(org.name)
        if summary.event_count == 0:
            return None
        if not (summary.total_reach > 0 and summary.total_revenue <= 0):
            return None
        # 既に収益化事業部があるなら構造追加はしない（目標設定の方に委ねる＝二重提案を避ける）。
        if any(d.type == DivisionType.MONETIZATION for d in org.divisions):
            return None
        plugin = get_division_plugin("note_monetization")
        if plugin is None or not isinstance(plugin.get("department"), dict):
            return None
        div_spec = _plugin_department_to_division_spec(plugin["department"])
        return build_intervention_proposal(
            target_org=org,
            intervention_type=StructuralInterventionType.ADD_DIVISION.value,
            title=f"[HQ介入] {org.name} に収益化事業部を新設（成果ベース）",
            description=(
                f"成果分析: リーチ {summary.total_reach:.0f} に対し収益 0、かつ収益化事業部が未設置。"
                f"事業部プラグイン『{plugin.get('label', plugin['id'])}』を追加して"
                "獲得を収益へ転換する（マーケットプレイスからも追加可能）。"
            ),
            intervention_spec={"division": div_spec, "plugin_id": plugin["id"]},
            source_org_name=self._source,
            target_ref="add_monetization_division",
        )

    def _intervention_from_outcomes(self, org: Organization) -> Optional[ImprovementProposal]:
        """成果フィードバックに基づく介入（閉じたフライホイール）。

        リーチ（インプレッション/クリック等）は出ているのに収益（売上/CV）が 0 の収益 org に対し、
        収益化を組織目標に設定する SET_GOAL 介入を提案する。
        """
        from core.metrics.outcomes import OutcomeStore

        summary = OutcomeStore(platform_home=self._psm.platform_home).summary_for_org(org.name)
        if summary.event_count == 0:
            return None
        if summary.total_reach > 0 and summary.total_revenue <= 0:
            return build_intervention_proposal(
                target_org=org,
                intervention_type=StructuralInterventionType.SET_GOAL.value,
                title=f"[HQ介入] {org.name} の収益化を目標化（成果ベース）",
                description=(
                    f"成果分析: リーチ {summary.total_reach:.0f} に対し収益 0。"
                    "獲得を収益に転換する施策（オファー/アフィリエイト最適化）を組織目標に設定する。"
                ),
                intervention_spec={
                    "goal": "リーチを収益へ転換する（オファー設計・アフィリエイト/CV 最適化）",
                    "target_category": "performance",
                },
                source_org_name=self._source,
                target_ref="monetization_from_outcomes",
            )
        return None

    def propose_all(
        self, *, persist: bool = True, dry_run: bool = False
    ) -> List[ImprovementProposal]:
        """全子 org を診断して構造介入提案を生成（既存 dedupe_key は除外）。

        persist=True かつ dry_run=False のとき、各提案を対象 org の .pantheon に保存する。
        """
        created: List[ImprovementProposal] = []
        for org in self.list_target_orgs():
            sm = self._psm.get_org_state_manager(org)
            existing = self._existing_dedupe_keys(sm)
            for proposal in self.propose_for_org(org):
                if proposal.dedupe_key and proposal.dedupe_key in existing:
                    continue
                existing.add(proposal.dedupe_key)
                if persist and not dry_run:
                    sm.save_improvement_proposal(proposal)
                created.append(proposal)
        return created

    # ------------------------------------------------------------------ #
    # 弱み → 介入の写像（決定論的ヒューリスティック）                      #
    # ------------------------------------------------------------------ #

    def _intervention_for_weakness(
        self, org: Organization, weakness: str, report: DiagnosticReport
    ) -> Optional[ImprovementProposal]:
        if weakness == _WEAKNESS_LOW_AUTONOMY:
            spec: Dict[str, Any] = {
                "division": {
                    "name": "実行強化部",
                    "type": "performance_optimization",
                    "mission": "小さく速い改善サイクルで自律スコアを引き上げる",
                    "teams": [
                        {
                            "name": "Execution Acceleration Team",
                            "mission": "高速な改善提案の生成と適用を主導する",
                            "agents": [
                                {
                                    "name": "Execution Strategist",
                                    "skills": ["performance_analysis", "strategic_planning"],
                                    "description": "実行ボトルネックを特定し改善を加速する",
                                }
                            ],
                        }
                    ],
                }
            }
            return build_intervention_proposal(
                target_org=org,
                intervention_type=StructuralInterventionType.ADD_DIVISION.value,
                title=f"[HQ介入] {org.name} に実行強化部を新設",
                description=(
                    f"診断: {weakness}（health={report.health_score:.0f}）。"
                    "高速な改善サイクルを主導する Performance Optimization Division を追加して自律性を底上げする。"
                ),
                intervention_spec=spec,
                source_org_name=self._source,
                target_ref="実行強化部",
            )

        if weakness == _WEAKNESS_LOW_KNOWLEDGE:
            spec = {
                "division": {
                    "name": "知識蓄積部",
                    "type": "knowledge_management",
                    "mission": "学びを継続的にナレッジ化し再利用する",
                    "teams": [
                        {
                            "name": "Knowledge Curation Team",
                            "mission": "重要な学びを毎週ナレッジとして記録・整理する",
                            "agents": [
                                {
                                    "name": "Knowledge Curator",
                                    "skills": ["knowledge_curation", "deep_research"],
                                    "description": "学びを抽出して再利用可能な知識に変換する",
                                }
                            ],
                        }
                    ],
                }
            }
            return build_intervention_proposal(
                target_org=org,
                intervention_type=StructuralInterventionType.ADD_DIVISION.value,
                title=f"[HQ介入] {org.name} に知識蓄積部を新設",
                description=(
                    f"診断: {weakness}。Knowledge Management Division を追加し、"
                    "学びの記録と再利用を仕組み化する。"
                ),
                intervention_spec=spec,
                source_org_name=self._source,
                target_ref="知識蓄積部",
            )

        if weakness == _WEAKNESS_LOW_QUALITY:
            spec = {
                "goal": "却下理由を分析し、提案テンプレートを改善して提案の採択率を高める",
                "target_category": "maintainability",
            }
            return build_intervention_proposal(
                target_org=org,
                intervention_type=StructuralInterventionType.SET_GOAL.value,
                title=f"[HQ介入] {org.name} の提案品質改善を目標化",
                description=(
                    f"診断: {weakness}。却下が採択を上回るため、提案品質向上を組織目標に設定する。"
                ),
                intervention_spec=spec,
                source_org_name=self._source,
                target_ref="proposal_quality",
            )

        return None

    # ------------------------------------------------------------------ #
    # メトリクス収集                                                      #
    # ------------------------------------------------------------------ #

    def _proposal_counts(self, sm: "RepoStateManager") -> tuple[int, int]:
        accepted = 0
        rejected = 0
        improvements_dir = sm.state_dir / "improvements"
        if not improvements_dir.exists():
            return (0, 0)
        for path in improvements_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            status = data.get("status")
            if status == "done":
                accepted += 1
            elif status == "rejected":
                rejected += 1
        return (accepted, rejected)

    def _knowledge_count(self, sm: "RepoStateManager") -> int:
        knowledge_dir = sm.state_dir / "knowledge"
        if not knowledge_dir.exists():
            return 0
        return sum(1 for _ in knowledge_dir.glob("*.json"))

    def _existing_dedupe_keys(self, sm: "RepoStateManager") -> set[str]:
        keys: set[str] = set()
        improvements_dir = sm.state_dir / "improvements"
        if not improvements_dir.exists():
            return keys
        for path in improvements_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if data.get("category") == STRUCTURAL_INTERVENTION_CATEGORY:
                key = data.get("dedupe_key")
                if key:
                    keys.add(key)
        return keys
