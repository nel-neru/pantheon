"""
ConfigAutoTuner — 設定自動チューニング (H-05)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from core.paths import resource_path


@dataclass
class TuningRecommendation:
    parameter: str
    current_value: object
    recommended_value: object
    reason: str


class ConfigAutoTuner:
    def __init__(self, config_path: Path = None):
        self.config_path = (
            Path(config_path) if config_path else resource_path("config", "default.yaml")
        )
        self._config = self._load_config()

    def analyze_and_recommend(
        self, health_scores: list[float], accepted_rates: list[float]
    ) -> list[TuningRecommendation]:
        recommendations: list[TuningRecommendation] = []
        avg_health = sum(health_scores) / len(health_scores) if health_scores else 0.0
        avg_acceptance = sum(accepted_rates) / len(accepted_rates) if accepted_rates else 0.0

        strictness = self._config.get("self_improvement", {}).get("review_strictness", {})
        cycle = self._config.get("self_improvement", {}).get("improvement_cycle", {})

        if avg_health < 40:
            recommendations.append(
                TuningRecommendation(
                    parameter="low_health_threshold",
                    current_value=strictness.get("low_health_threshold"),
                    recommended_value=35,
                    reason="Average health score is below 40; lower the threshold to react earlier.",
                )
            )

        if avg_acceptance < 0.3:
            recommendations.append(
                TuningRecommendation(
                    parameter="review_cycles",
                    current_value=cycle.get("default_max_cycles"),
                    recommended_value=max(int(cycle.get("default_max_cycles", 3)) + 1, 4),
                    reason="Acceptance rate is below 30%; add more review cycles to improve proposal quality.",
                )
            )

        return recommendations

    def format_recommendations(self, recs: list[TuningRecommendation]) -> str:
        if not recs:
            return "No config tuning recommendations."
        return "\n".join(
            f"- {rec.parameter}: {rec.current_value} -> {rec.recommended_value} ({rec.reason})"
            for rec in recs
        )

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            return {}
        data = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        return data or {}
