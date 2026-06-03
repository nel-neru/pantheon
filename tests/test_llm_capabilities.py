"""Tests for ProviderCapabilities (core/llm/capabilities.py)."""

from __future__ import annotations

import pytest

from core.llm import (
    AnthropicProvider,
    GeminiProvider,
    GitHubModelsProvider,
    OpenAIProvider,
    ProviderCapabilities,
    all_capabilities,
    get_capabilities,
)
from core.llm.capabilities import CAPABILITIES

ALL_PROVIDERS = ["anthropic", "openai", "groq", "github_models", "gemini"]


@pytest.mark.parametrize("provider", ALL_PROVIDERS)
def test_every_provider_has_capabilities(provider):
    cap = get_capabilities(provider)
    assert isinstance(cap, ProviderCapabilities)
    assert cap.provider == provider
    assert cap.max_context_tokens > 0


def test_unknown_provider_returns_default_with_name():
    cap = get_capabilities("some-future-provider")
    assert cap.provider == "some-future-provider"
    assert isinstance(cap, ProviderCapabilities)


def test_to_dict_roundtrip_keys():
    cap = get_capabilities("anthropic")
    data = cap.to_dict()
    assert data["provider"] == "anthropic"
    assert "supports_tools" in data
    assert "supports_streaming" in data
    assert "max_context_tokens" in data


def test_all_capabilities_covers_registry():
    data = all_capabilities()
    assert set(data.keys()) == set(CAPABILITIES.keys())
    assert set(data.keys()) == set(ALL_PROVIDERS)


def test_provider_instances_expose_capabilities():
    assert AnthropicProvider().capabilities.provider == "anthropic"
    assert OpenAIProvider(provider_name="openai").capabilities.provider == "openai"
    assert OpenAIProvider(provider_name="groq").capabilities.provider == "groq"
    assert GitHubModelsProvider().capabilities.provider == "github_models"
    assert GeminiProvider().capabilities.provider == "gemini"


def test_all_providers_support_tools_and_streaming():
    # 全プロバイダーで tool 呼び出しとストリーミングの経路がある
    for provider in ALL_PROVIDERS:
        cap = get_capabilities(provider)
        assert cap.supports_tools is True
        assert cap.supports_streaming is True
