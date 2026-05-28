"""
RepoCorp AI - Central Orchestrator (Platform Level)

PlatformStateManager を使い、全 Organization（子会社）を横断的に管理する。
各 Organization はそれぞれの target_repo_path を持ち、自律的に改善サイクルを回す。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from core.metrics.balanced_growth import calculate_group_metrics, calculate_organization_metrics
from core.models.organization import (
    GroupHQState,
    Organization,
    OrganizationMetrics,
    OrganizationStatus,
)
from core.platform.state import PlatformStateManager
from core.state.manager import RepoStateManager


class RepoCorpOrchestrator:
    """
    Core（本社）レベルのオーケストレーター

    PlatformStateManager を通じて全 Organization を管理し、
    GroupOrchestrator と連携してメトリクス駆動の改善サイクルを実行する。
    """

    def __init__(
        self,
        platform_state_manager: Optional[PlatformStateManager] = None,
    ):
        self._psm = platform_state_manager or PlatformStateManager()
        self.state = GroupHQState()
        self._org_state_managers: Dict[str, RepoStateManager] = {}
        self._lock = asyncio.Lock()
        self._load_organizations()

    def _load_organizations(self) -> None:
        """グローバルストアから全 Organization を読み込む"""
        for org in self._psm.load_organizations():
            self.state.add_organization(org)
            self._org_state_managers[str(org.id)] = self._psm.get_org_state_manager(org)

    @classmethod
    def from_platform(cls) -> "RepoCorpOrchestrator":
        """グローバルプラットフォームからオーケストレーターを初期化する"""
        return cls(PlatformStateManager())

    async def create_organization(
        self,
        name: str,
        purpose: str = "",
        target_repo_path: str = "",
        template_name: Optional[str] = None,
    ) -> Organization:
        """新しい Organization（子会社）を立ち上げてグローバルに登録する"""
        from core.org_factory import create_organization_from_template, create_default_organization

        async with self._lock:
            if template_name:
                template_path = Path(__file__).parent.parent / "config" / "departments" / f"{template_name}.yaml"
                org = create_organization_from_template(name, purpose, template_path)
            else:
                org = create_default_organization(name, purpose)

            org.target_repo_path = target_repo_path

            self.state.add_organization(org)
            self._psm.save_organization(org)
            self._org_state_managers[str(org.id)] = self._psm.get_org_state_manager(org)

            print(f"[Orchestrator] 新 Organization を設立しました: {name} → {target_repo_path or '(未設定)'}")
            return org

    async def get_organization_status(self, org_id: UUID) -> Optional[Dict[str, Any]]:
        """Organization ID を指定して現在の状態を取得"""
        org = self.state.organizations.get(org_id)
        if not org:
            return None
        sm = self._org_state_managers.get(str(org_id))
        pending = len(sm.get_pending_improvement_proposals(limit=100)) if sm else 0
        metrics = calculate_organization_metrics(org, pending_proposals_count=pending)
        return {
            "id": str(org.id),
            "name": org.name,
            "purpose": org.purpose,
            "target_repo_path": org.target_repo_path,
            "status": org.status.value,
            "health_score": metrics.health_score,
            "autonomy_score": org.autonomy_score,
            "improvement_velocity": org.improvement_velocity,
            "total_agents": len(org.get_all_agents()),
            "pending_proposals": pending,
        }

    async def run_meta_evolution_cycle(
        self,
        max_organizations: int = 3,
        max_cycles_per_org: int = 2,
    ) -> Dict[str, Any]:
        """Core 主導の自己改善サイクルを全 Organization に対して実行する"""
        from core.orchestration.group_orchestrator import GroupOrchestrator

        async with self._lock:
            group_orch = GroupOrchestrator(self.state)
            for org_id, sm in self._org_state_managers.items():
                group_orch.register_state_manager(org_id, sm)

            await group_orch.run_smart_improvement_cycle(
                max_organizations=max_organizations,
                max_cycles_per_org=max_cycles_per_org,
            )
            summary = group_orch.get_group_status_summary()
            return {
                "total_organizations": len(self.state.organizations),
                "group_health_score": self.state.group_health_score,
                "group_metrics": summary,
            }

    async def list_organizations(
        self, status: Optional[OrganizationStatus] = None
    ) -> List[Dict[str, Any]]:
        """登録されている全 Organization を返す"""
        result = []
        for org in self.state.organizations.values():
            if status is None or org.status == status:
                sm = self._org_state_managers.get(str(org.id))
                pending = len(sm.get_pending_improvement_proposals(limit=100)) if sm else 0
                metrics = calculate_organization_metrics(org, pending_proposals_count=pending)
                result.append({
                    "id": str(org.id),
                    "name": org.name,
                    "purpose": org.purpose,
                    "target_repo_path": org.target_repo_path,
                    "status": org.status.value,
                    "health_score": metrics.health_score,
                    "autonomy_score": org.autonomy_score,
                    "improvement_velocity": org.improvement_velocity,
                    "total_agents": len(org.get_all_agents()),
                    "pending_proposals": pending,
                    "last_active": org.last_active.isoformat(),
                })
        return result

    def get_global_state_summary(self) -> Dict[str, Any]:
        """プラットフォーム全体のサマリー"""
        org_metrics = [
            calculate_organization_metrics(
                org,
                pending_proposals_count=len(
                    self._org_state_managers[str(org.id)].get_pending_improvement_proposals(limit=100)
                ) if str(org.id) in self._org_state_managers else 0,
            )
            for org in self.state.organizations.values()
        ]
        group = calculate_group_metrics(self.state, org_metrics)
        return {
            "version": self.state.version,
            "total_organizations": len(self.state.organizations),
            "total_agents": self.state.total_agents,
            "group_health_score": group.group_health_score,
            "balance_score": group.balance_score,
            "weakest_organization": group.weakest_organization,
            "strongest_organization": group.strongest_organization,
            "platform_home": str(self._psm.platform_home),
            "last_updated": self.state.last_updated.isoformat(),
        }
