"""
自己改善ループ用に、Pre-Task メタ分析・能力レジストリ・パターン学習・AgentFactory を
配線した PreTaskOrchestrator を組み立てるヘルパー。

SelfImprovementLoop はこれを使うことで、ハードコードした agents[0] ではなく
CapabilityRegistry / TaskRouter のスキルマッチで適切な SpecialistAgent を選び、
実行結果（品質スコア・所要時間）を OrchestrationPatternStore / CapabilityRegistry に
フィードバックできる。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def build_improvement_orchestrator(*, platform_home: Optional[Path] = None):
    """配線済みの ``(PreTaskOrchestrator, AgentFactory)`` を返す。

    CapabilityRegistry のスキャンに失敗しても、ルーティングのフォールバックで
    最低限 ``agent:improvement_executor`` を選べるよう例外は握り潰す。
    """
    from agents.agent_factory import AgentFactory
    from core.intelligence.capability_registry import CapabilityRegistry
    from core.orchestration.orchestration_pattern_store import OrchestrationPatternStore
    from core.orchestration.pre_task_orchestrator import PreTaskOrchestrator

    registry = CapabilityRegistry(platform_home=platform_home)
    try:
        registry.scan_and_register_all()
    except Exception:  # noqa: BLE001 - スキャン不能でもフォールバックで動作させる
        pass

    store = OrchestrationPatternStore(platform_home=platform_home)
    factory = AgentFactory()
    orchestrator = PreTaskOrchestrator(
        capability_registry=registry,
        pattern_store=store,
        agent_factory=factory,
    )
    return orchestrator, factory
