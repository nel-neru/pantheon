"""Tests for the model tier router (core.runtime.model_router)."""

from __future__ import annotations

import pytest

from core.runtime.model_router import (
    DEFAULT_TASK_TIERS,
    ModelTierRouter,
    TierRules,
    load_rules,
    reset_router,
)


@pytest.fixture(autouse=True)
def _fresh_router():
    reset_router()
    yield
    reset_router()


def test_default_task_routing():
    router = ModelTierRouter(TierRules())
    assert router.select("improvement_execution") == "fable"
    assert router.select("meta_improvement") == "fable"
    assert router.select("code_review") == "sonnet"
    assert router.select("content_generation") == "sonnet"
    assert router.select("conversation") == "haiku"
    assert router.select("compaction") == "haiku"
    # 不明な task_type は default_tier（standard）
    assert router.select("unknown_task") == "sonnet"
    assert router.select(None) == "sonnet"


def test_escalation_on_large_prompt():
    router = ModelTierRouter(TierRules())
    assert router.select("code_review", prompt_chars=30000) == "fable"
    assert router.select("conversation", prompt_chars=30000) == "sonnet"
    # 既に最上位ティアならそのまま（範囲外に飛ばない）
    assert router.select("improvement_execution", prompt_chars=30000) == "fable"


def test_downgrade_for_quota_pressure():
    router = ModelTierRouter(TierRules())
    assert router.select("code_review", downgrade=True) == "haiku"
    # 既に最下位ならそのまま
    assert router.select("conversation", downgrade=True) == "haiku"


def test_kill_switch_disables_routing(monkeypatch):
    monkeypatch.setenv("PANTHEON_MODEL_ROUTING", "0")
    router = ModelTierRouter(TierRules())
    assert router.select("improvement_execution") is None


def test_load_rules_from_yaml(tmp_path):
    cfg = tmp_path / "model_tiers.yaml"
    cfg.write_text(
        "tiers:\n  heavy: opus\n  standard: sonnet\n  light: haiku\n"
        "default_tier: light\n"
        "task_tiers:\n  custom_task: heavy\n"
        "escalate_above_prompt_chars: 5\n",
        encoding="utf-8",
    )
    router = ModelTierRouter(load_rules(cfg))
    assert router.select("custom_task") == "opus"
    assert router.select("unknown") == "haiku"  # default_tier: light
    assert router.select("unknown", prompt_chars=10) == "sonnet"  # 5 文字超でエスカレーション
    # 内蔵デフォルトはマージで維持される
    assert router.select("improvement_execution") == "opus"


def test_load_rules_broken_yaml_falls_back(tmp_path):
    cfg = tmp_path / "model_tiers.yaml"
    cfg.write_text("{not yaml", encoding="utf-8")
    rules = load_rules(cfg)
    assert rules.task_tiers == DEFAULT_TASK_TIERS
    assert ModelTierRouter(rules).select("code_review") == "sonnet"


def test_bundled_config_loads():
    # リポジトリ同梱の config/model_tiers.yaml が内蔵デフォルトと整合している
    # （heavy ティアは Fable 5 = 長時間自律実行用。Master Plan §9）
    rules = load_rules()
    assert rules.tier_models == {"heavy": "fable", "standard": "sonnet", "light": "haiku"}
    assert rules.task_tiers["improvement_execution"] == "heavy"
    assert rules.escalate_above_prompt_chars == 20000
