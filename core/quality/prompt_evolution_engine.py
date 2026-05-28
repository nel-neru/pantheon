"""
PromptEvolutionEngine — プロンプト自己改善エンジン (H-02~H-03)

エージェントのプロンプトを実行結果から評価・改善する。
A/Bテスト基盤と自己改善サイクルを提供する。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.platform.state import get_platform_home


@dataclass
class PromptVariant:
    variant_id: str
    prompt_text: str
    use_count: int = 0
    success_count: int = 0
    avg_quality: float = 0.0


@dataclass
class PromptExperiment:
    experiment_id: str
    agent_name: str
    variants: list[PromptVariant] = field(default_factory=list)
    created_at: str = ""


class PromptEvolutionEngine:
    """Stores prompt experiments and derives simple improvements from outcomes."""

    def __init__(self, platform_home: Path = None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.experiments_file = self.platform_home / "prompt_experiments.json"
        self._experiments = self._load()

    def create_experiment(self, agent_name: str, prompt_a: str, prompt_b: str) -> PromptExperiment:
        experiment = PromptExperiment(
            experiment_id=str(uuid4()),
            agent_name=agent_name,
            variants=[
                PromptVariant(variant_id="A", prompt_text=prompt_a),
                PromptVariant(variant_id="B", prompt_text=prompt_b),
            ],
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._experiments[experiment.experiment_id] = experiment
        self._save()
        return experiment

    def record_result(self, experiment_id: str, variant_id: str, success: bool, quality: float) -> None:
        experiment = self._experiments.get(experiment_id)
        if experiment is None:
            return
        for variant in experiment.variants:
            if variant.variant_id != variant_id:
                continue
            total_quality = variant.avg_quality * variant.use_count + quality
            variant.use_count += 1
            variant.success_count += 1 if success else 0
            variant.avg_quality = total_quality / variant.use_count
            self._save()
            return

    def get_best_variant(self, experiment_id: str) -> PromptVariant | None:
        experiment = self._experiments.get(experiment_id)
        if experiment is None or not experiment.variants:
            return None
        if any(variant.use_count < 3 for variant in experiment.variants):
            return None
        return max(
            experiment.variants,
            key=lambda variant: (variant.success_count / variant.use_count) * variant.avg_quality,
        )

    def evolve_prompt(self, base_prompt: str, performance_history: list[dict]) -> str:
        if not performance_history:
            return base_prompt
        qualities = [float(item.get("quality", 0.0)) for item in performance_history if "quality" in item]
        if not qualities:
            return base_prompt
        avg_quality = sum(qualities) / len(qualities)
        if avg_quality < 6:
            return self._append_hint(base_prompt, "より具体的で実装可能な提案を心がけてください。")
        if avg_quality >= 8:
            return self._append_hint(base_prompt, "現在の高品質を維持してください。")
        return base_prompt

    def _append_hint(self, base_prompt: str, hint: str) -> str:
        if hint in base_prompt:
            return base_prompt
        separator = "\n\n" if base_prompt else ""
        return f"{base_prompt}{separator}{hint}"

    def _load(self) -> dict[str, PromptExperiment]:
        if not self.experiments_file.exists():
            return {}
        payload = json.loads(self.experiments_file.read_text(encoding="utf-8"))
        experiments: dict[str, PromptExperiment] = {}
        for item in payload.get("experiments", []):
            variants = [PromptVariant(**variant) for variant in item.get("variants", [])]
            experiment = PromptExperiment(
                experiment_id=item["experiment_id"],
                agent_name=item["agent_name"],
                variants=variants,
                created_at=item.get("created_at", ""),
            )
            experiments[experiment.experiment_id] = experiment
        return experiments

    def _save(self) -> None:
        payload = {
            "experiments": [asdict(experiment) for experiment in self._experiments.values()]
        }
        self.experiments_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
