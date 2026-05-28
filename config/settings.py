"""
RepoCorp AI - 外部設定管理（YAML対応）

将来的に商品化を見据え、ルールや閾値をコードから分離して管理する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic import BaseModel, Field


class ReviewStrictnessConfig(BaseModel):
    base_level: str = "very_strict"
    dynamic_adjustment: bool = True
    low_health_threshold: int = 50
    medium_health_threshold: int = 70


class HumanInLoopConfig(BaseModel):
    enabled: bool = True
    auto_approve_below_priority: str = "medium"
    timeout_minutes: int = 60


class ImprovementCycleConfig(BaseModel):
    max_cycles_per_sub: int = 5
    stop_if_no_improvement_for: int = 2
    default_max_cycles: int = 3


class MetricsConfig(BaseModel):
    health_score_weights: Dict[str, float] = Field(
        default_factory=lambda: {"autonomy": 0.4, "velocity": 0.3, "review_score": 0.3}
    )


class SelfImprovementConfig(BaseModel):
    review_strictness: ReviewStrictnessConfig = Field(default_factory=ReviewStrictnessConfig)
    human_in_loop: HumanInLoopConfig = Field(default_factory=HumanInLoopConfig)
    improvement_cycle: ImprovementCycleConfig = Field(default_factory=ImprovementCycleConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)


class AppConfig(BaseModel):
    self_improvement: SelfImprovementConfig = Field(default_factory=SelfImprovementConfig)
    # 将来的に他の設定（部署テンプレート、ワーカースキルなど）もここに追加


def load_config(config_path: str | Path = "config/default.yaml") -> AppConfig:
    """YAMLから設定を読み込む"""
    path = Path(config_path)
    if not path.exists():
        # デフォルト設定を返す
        return AppConfig()

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return AppConfig(**data)


# グローバル設定（起動時に一度読み込む想定）
config: AppConfig = load_config()
