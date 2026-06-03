"""Tests for the consolidated model registry (core/llm/model_registry.py)."""

from __future__ import annotations

import pytest

from core.llm.model_registry import (
    DEFAULT_MODELS,
    FALLBACK_MODELS,
    TASK_MODELS,
    get_default_model,
    get_fallback_models,
    get_task_model,
    known_providers,
)

PROVIDERS = ["anthropic", "openai", "groq", "github_models", "gemini"]


def test_known_providers():
    assert set(known_providers()) == set(PROVIDERS)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_fallback_models_non_empty(provider):
    models = get_fallback_models(provider)
    assert models and all(isinstance(m, str) for m in models)


def test_fallback_models_unknown_provider_is_empty():
    assert get_fallback_models("nope") == []


@pytest.mark.parametrize("provider", PROVIDERS)
def test_default_model_is_in_fallback_list(provider):
    assert get_default_model(provider) in FALLBACK_MODELS[provider]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_task_model_resolution(provider):
    assert get_task_model(provider, "fast") in FALLBACK_MODELS[provider]
    assert get_task_model(provider, "reasoning") in FALLBACK_MODELS[provider]
    # 未知タスクは default にフォールバック
    assert get_task_model(provider, "unknown-task") == TASK_MODELS[provider]["default"]


def test_registries_share_provider_keys():
    assert set(DEFAULT_MODELS.keys()) == set(FALLBACK_MODELS.keys())
    assert set(TASK_MODELS.keys()) == set(FALLBACK_MODELS.keys())


def test_server_uses_registry_fallback_models():
    pytest.importorskip("fastapi")
    import web.server as server

    assert server.FALLBACK_MODELS is FALLBACK_MODELS
