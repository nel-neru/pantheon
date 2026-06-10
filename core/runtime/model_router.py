"""ModelTierRouter — task_type と入力規模から claude CLI の ``--model`` を自動選択する。

「トークンを無駄にしない」ためのモデル使い分けの中枢。ティアは alias
（opus/sonnet/haiku）で指定し、モデル ID の世代交代に追従不要とする。
優先順位は呼び出し側（:func:`core.runtime.claude_code.run_claude_sync`）で

    明示 ``model`` 引数 ＞ 本ルーター ＞ ``PANTHEON_DEFAULT_MODEL``

となる。``PANTHEON_MODEL_ROUTING=0`` で全体を無効化（キルスイッチ）。
ルールは ``config/model_tiers.yaml`` から読み込み、欠落・破損時は内蔵
デフォルトで動く（設定ミスが生成を止めることはない）。
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

ROUTING_ENV = "PANTHEON_MODEL_ROUTING"
CONFIG_FILENAME = "model_tiers.yaml"

TIER_ORDER = ("light", "standard", "heavy")

DEFAULT_TIER_MODELS: Dict[str, str] = {"heavy": "opus", "standard": "sonnet", "light": "haiku"}
DEFAULT_TASK_TIERS: Dict[str, str] = {
    "improvement_execution": "heavy",
    "meta_improvement": "heavy",
    "security_audit": "heavy",
    "code_review": "standard",
    "quality_review": "standard",
    "content_generation": "standard",
    "codebase_exploration": "standard",
    "conversation": "light",
    "compaction": "light",
    "scoring": "light",
    "summarize": "light",
}
DEFAULT_TIER = "standard"
DEFAULT_ESCALATE_CHARS = 20000


def routing_enabled() -> bool:
    return os.getenv(ROUTING_ENV, "1").strip().lower() not in {"0", "false", "off", "no"}


@dataclass(frozen=True)
class TierRules:
    tier_models: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_TIER_MODELS))
    task_tiers: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_TASK_TIERS))
    default_tier: str = DEFAULT_TIER
    escalate_above_prompt_chars: int = DEFAULT_ESCALATE_CHARS


def _config_path() -> Path:
    from core.paths import resource_path

    return resource_path("config", CONFIG_FILENAME)


def load_rules(path: Optional[Path] = None) -> TierRules:
    """yaml からルールを読み込む。欠落・破損時は内蔵デフォルト（生成を止めない）。"""
    path = path or _config_path()
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 - 設定不備はデフォルトで吸収
        logger.debug("model_tiers.yaml unavailable (%s) — using built-in defaults", exc)
        return TierRules()
    if not isinstance(data, dict):
        return TierRules()

    tier_models = dict(DEFAULT_TIER_MODELS)
    raw_tiers = data.get("tiers")
    if isinstance(raw_tiers, dict):
        tier_models.update({str(k): str(v) for k, v in raw_tiers.items() if v})

    task_tiers = dict(DEFAULT_TASK_TIERS)
    raw_tasks = data.get("task_tiers")
    if isinstance(raw_tasks, dict):
        task_tiers.update({str(k): str(v) for k, v in raw_tasks.items() if v})

    default_tier = str(data.get("default_tier") or DEFAULT_TIER)
    try:
        escalate = int(data.get("escalate_above_prompt_chars", DEFAULT_ESCALATE_CHARS))
    except (TypeError, ValueError):
        escalate = DEFAULT_ESCALATE_CHARS
    return TierRules(
        tier_models=tier_models,
        task_tiers=task_tiers,
        default_tier=default_tier,
        escalate_above_prompt_chars=escalate,
    )


def _shift_tier(tier: str, steps: int) -> str:
    try:
        idx = TIER_ORDER.index(tier)
    except ValueError:
        return tier
    return TIER_ORDER[max(0, min(len(TIER_ORDER) - 1, idx + steps))]


class ModelTierRouter:
    def __init__(self, rules: Optional[TierRules] = None):
        self._rules = rules or load_rules()

    def select(
        self,
        task_type: Optional[str],
        prompt_chars: int = 0,
        *,
        downgrade: bool = False,
    ) -> Optional[str]:
        """選択した ``--model`` alias。ルーティング無効時は ``None``。

        ``downgrade=True`` はレート逼迫時（A-5 quota governor）の 1 ティア降格指示。
        """
        if not routing_enabled():
            return None
        rules = self._rules
        tier = rules.task_tiers.get((task_type or "").strip(), rules.default_tier)
        if tier not in TIER_ORDER:
            tier = rules.default_tier if rules.default_tier in TIER_ORDER else DEFAULT_TIER
        if prompt_chars > rules.escalate_above_prompt_chars:
            tier = _shift_tier(tier, +1)  # 大きい入力は理解力優先で 1 ティア上げ
        if downgrade:
            tier = _shift_tier(tier, -1)
        return rules.tier_models.get(tier)


_router_lock = threading.Lock()
_router: Optional[ModelTierRouter] = None


def get_router() -> ModelTierRouter:
    global _router
    with _router_lock:
        if _router is None:
            _router = ModelTierRouter()
        return _router


def reset_router() -> None:
    """テスト・設定再読込用に共有ルーターを破棄する。"""
    global _router
    with _router_lock:
        _router = None


def select_model(
    task_type: Optional[str], prompt_chars: int = 0, *, downgrade: bool = False
) -> Optional[str]:
    return get_router().select(task_type, prompt_chars, downgrade=downgrade)
