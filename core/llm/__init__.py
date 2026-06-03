"""
RepoCorp AI - LLM Provider Package

使用例:
    from core.llm import get_llm_provider

    provider = get_llm_provider("anthropic")
    response = await provider.generate(messages=[...])
"""

from .anthropic_provider import AnthropicProvider
from .base import LLMConfig, LLMMessage, LLMProvider, LLMResponse
from .capabilities import ProviderCapabilities, all_capabilities, get_capabilities
from .client import (
    LLMClient,
    get_configured_llm_provider,
    get_default_llm_client,
    reset_provider_cache,
    resolve_default_model,
    resolve_default_provider,
    resolve_provider_api_key,
)
from .gemini_provider import GeminiProvider
from .github_models_provider import GitHubModelsProvider
from .json_extract import extract_json, extract_json_object
from .openai_provider import OpenAIProvider
from .retry import LLMError, call_with_retry, classify_exception
from .usage import get_usage_tracker, record_usage, reset_usage

__all__ = [
    "LLMProvider",
    "LLMMessage",
    "LLMResponse",
    "LLMConfig",
    "LLMClient",
    "AnthropicProvider",
    "OpenAIProvider",
    "GitHubModelsProvider",
    "GeminiProvider",
    "get_default_llm_client",
    "get_configured_llm_provider",
    "reset_provider_cache",
    "resolve_default_provider",
    "resolve_provider_api_key",
    "resolve_default_model",
    "extract_json_object",
    "extract_json",
    "ProviderCapabilities",
    "get_capabilities",
    "all_capabilities",
    "LLMError",
    "call_with_retry",
    "classify_exception",
    "get_usage_tracker",
    "record_usage",
    "reset_usage",
]


def get_llm_provider(
    provider_name: str | None = None,
    config: LLMConfig | None = None,
) -> LLMProvider:
    """プロバイダー名からインスタンスを返すファクトリ関数"""
    config = config or LLMConfig.from_env()
    selected_provider = provider_name or config.default_provider

    if selected_provider == "anthropic":
        return AnthropicProvider(config)
    if selected_provider in {"openai", "groq"}:
        return OpenAIProvider(config, provider_name=selected_provider)
    if selected_provider == "github_models":
        return GitHubModelsProvider(config)
    if selected_provider == "gemini":
        return GeminiProvider(config)
    raise ValueError(f"Unknown LLM provider: {selected_provider}")
