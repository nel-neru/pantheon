"""
OrganizationLifecycle — 成長段階管理と動作変化 (C-04)
INCUBATING → GROWING → MATURE → AUTONOMOUS
"""

from __future__ import annotations

from enum import Enum


class LifecycleStage(str, Enum):
    INCUBATING = "incubating"
    GROWING = "growing"
    MATURE = "mature"
    AUTONOMOUS = "autonomous"


STAGE_THRESHOLDS: dict[LifecycleStage, int] = {
    LifecycleStage.GROWING: 30,
    LifecycleStage.MATURE: 60,
    LifecycleStage.AUTONOMOUS: 80,
}


class OrganizationLifecycle:
    def determine_stage(self, autonomy_score: float) -> LifecycleStage:
        if autonomy_score >= STAGE_THRESHOLDS[LifecycleStage.AUTONOMOUS]:
            return LifecycleStage.AUTONOMOUS
        if autonomy_score >= STAGE_THRESHOLDS[LifecycleStage.MATURE]:
            return LifecycleStage.MATURE
        if autonomy_score >= STAGE_THRESHOLDS[LifecycleStage.GROWING]:
            return LifecycleStage.GROWING
        return LifecycleStage.INCUBATING

    def get_auto_approve_bonus(self, stage: LifecycleStage) -> float:
        bonuses = {
            LifecycleStage.INCUBATING: 0.0,
            LifecycleStage.GROWING: 0.1,
            LifecycleStage.MATURE: 0.2,
            LifecycleStage.AUTONOMOUS: 0.4,
        }
        return bonuses[stage]

    def get_review_intensity(self, stage: LifecycleStage) -> str:
        if stage in {LifecycleStage.INCUBATING, LifecycleStage.GROWING}:
            return "strict"
        if stage == LifecycleStage.MATURE:
            return "normal"
        return "light"

    def describe_stage(self, stage: LifecycleStage) -> str:
        descriptions = {
            LifecycleStage.INCUBATING: "立ち上げ段階。厳格なレビューと学習蓄積が必要です。",
            LifecycleStage.GROWING: "成長段階。改善提案が増え、継続的な監督が必要です。",
            LifecycleStage.MATURE: "成熟段階。安定運用しつつ、通常強度のレビューで回せます。",
            LifecycleStage.AUTONOMOUS: "自律段階。軽いレビューで高速に改善を進められます。",
        }
        return descriptions[stage]
